import json
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# from tqdm import tqdm  <-- 把这行注释掉
def tqdm(iterable, **kwargs): return iterable # <-- 加上这一行，这就叫“假进度条”

# ================= 配置区 =================
DATA_FILE = "my_ao3_db.json"
USER_DATA_DIR = "chrome_user_data"
# =========================================

def parse_int(s):
    """提取字符串中的数字"""
    if not s: return 0
    return int(re.sub(r"[^\d]", "", s))

def clean_text(text):
    return text.strip() if text else ""

def get_categories(soup):
    """提取分类 (Category) - 返回列表"""
    tags = soup.select("ul.required-tags span.category")
    cats = []
    for tag in tags:
        val = tag.get("title", "").strip()
        if val: cats.append(val)
    return cats if cats else ["Unknown"]

def get_rating(soup):
    """提取分级 (Rating)"""
    tag = soup.select_one("ul.required-tags span.rating")
    return tag["title"].strip() if tag and tag.get("title") else "Unknown"

def get_recursive_comments(soup, current_chapter_default=1):
    """递归解析评论树 (带精准的 chapter_index)"""
    comments_flat_list = []

    def parse_thread(thread_ol, parent_id=None, current_chapter_idx=current_chapter_default):
        if not thread_ol: return

        all_lis = thread_ol.find_all("li", recursive=False)
        i = 0
        while i < len(all_lis):
            li = all_lis[i]
            raw_id = li.get("id")
            
            if raw_id and raw_id.startswith("comment_"):
                my_id = raw_id.replace("comment_", "")
                user = "Guest"
                chapter_idx = current_chapter_idx 
                chapter_name = f"Chapter {chapter_idx}"
                date_str = ""
                
                byline = li.find("h4", class_="byline")
                if byline:
                    user_link = byline.find("a", href=re.compile(r"^/users/"))
                    if user_link: user = user_link.get_text(strip=True)
                    
                    # 精确提取章节 Index
                    byline_text = byline.get_text()
                    match = re.search(r"on Chapter\s+(\d+)", byline_text)
                    if match:
                        chapter_idx = int(match.group(1))
                        chapter_name = f"Chapter {chapter_idx}"
                    else:
                        chapter_idx = 1
                        chapter_name = "Chapter 1"

                dt_span = li.find("span", class_="datetime")
                if dt_span: date_str = dt_span.get_text(strip=True)

                block = li.find("blockquote", class_="userstuff")
                text_content = clean_text(block.get_text("\n")) if block else "[Deleted/Hidden]"

                comments_flat_list.append({
                    "id": my_id,
                    "parent_id": parent_id,
                    "user": user,
                    "chapter_index": chapter_idx,
                    "chapter_name": chapter_name,
                    "date": date_str,
                    "text": text_content[:500] 
                })
                
                if i + 1 < len(all_lis):
                    next_li = all_lis[i + 1]
                    if not next_li.get("id"): 
                        reply_ol = next_li.find("ol", class_="thread")
                        if reply_ol:
                            parse_thread(reply_ol, parent_id=my_id, current_chapter_idx=chapter_idx)
                            i += 1 
            i += 1

    placeholder = soup.find("div", id="comments_placeholder")
    if placeholder:
        root_thread = placeholder.find("ol", class_="thread", recursive=False)
        if root_thread:
            parse_thread(root_thread)
    
    return comments_flat_list

def main():
    print("🚀 AO3 年度总结抓取工具 [v2.3 Unrevealed Fix]")
    print("✨ 修复: Unrevealed作品也能正确抓取完整章节列表")
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False, 
            viewport={'width': 1280, 'height': 800}
        )
        page = context.pages[0]

        # ================= 1. 登录验证 =================
        print("🔗 正在验证身份...")
        page.goto("https://archiveofourown.org/")
        
        user_greeting = page.locator("#greeting ul.user.navigation a[href^='/users/']").first
        if user_greeting.count() == 0:
            print("\n🚨 请先手动登录 (勾选Remember Me)，完成后按回车...")
            input()
            page.reload()
            user_greeting = page.locator("#greeting ul.user.navigation a[href^='/users/']").first
            if user_greeting.count() == 0:
                print("❌ 登录失败，退出。")
                context.close()
                return

        href_val = user_greeting.get_attribute("href") 
        current_user = href_val.split("/")[-1]
        print(f"✅ 当前用户: 【{current_user}】")

        full_data = {
            "account": {
                "username": current_user,
                "fetch_time": datetime.now().isoformat(),
            },
            "works": []
        }

        # ================= 2. Stats (隐形数据) =================
        print("\n📊 [1/3] 获取 Stats (订阅/收藏)...")
        stats_map = {}
        try:
            page.goto(f"https://archiveofourown.org/users/{current_user}/stats")
            soup = BeautifulSoup(page.content(), "html.parser")
            for lnk in soup.select("a[href*='/works/']"):
                row = lnk.find_parent("li")
                if not row: continue
                wid = lnk['href'].split("/")[-1]
                txt = row.get_text()
                if wid not in stats_map:
                    subs = parse_int(re.search(r"Subscriptions:\s*(\d+)", txt).group(1)) if "Subscriptions:" in txt else 0
                    bms = parse_int(re.search(r"Bookmarks:\s*(\d+)", txt).group(1)) if "Bookmarks:" in txt else 0
                    stats_map[wid] = {"subs": subs, "bookmarks": bms}
        except Exception as e:
            print(f"   ⚠️ Stats 获取失败: {e}")

        # ================= 3. 扫描列表 (Meta信息) =================
        print("\n📋 [2/3] 扫描作品列表...")
        work_list_skeleton = []

        def scan_list(url_suffix, label, max_pages=10):
            base_url = f"https://archiveofourown.org/users/{current_user}/{url_suffix}"
            print(f"   > 扫描 {label} ...")
            page_num = 1
            try:
                while page_num <= max_pages:
                    url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
                    print(f"     - Page {page_num}")
                    page.goto(url, timeout=60000)
                    # page.goto(base_url)
                    if page.locator("text='Proceed'").count() > 0: page.click("text='Proceed'")
                    
                    soup = BeautifulSoup(page.content(), "html.parser")
                    items = soup.select("li.own.work.blurb") 
                    if not items:
                        return
                
                    for item in items:
                        # 1. 获取更新日期并进行年份检查
                        dt = item.find("p", class_="datetime")
                        if not dt:
                            continue
                        date_text = dt.text.strip()
                        # 格式通常为 "18 Dec 2025"
                        
                        try:
                            # 提取末尾的 4 位数字年份
                            year_match = re.search(r"(\d{4})$", date_text)
                            if year_match:
                                year = int(year_match.group(1))
                                if year < 2025:
                                    print(f"  🛑 发现 {year} 年作品，停止扫描该列表。")
                                    return # 直接跳出当前的 scan_list 函数
                        except Exception:
                            pass # 如果解析失败，稳妥起见继续往下走

                        h4 = item.find("h4", class_="heading")
                        if not h4: continue
                        link = h4.find('a')
                        wid = link['href'].split("/")[-1]
                        title = link.text.strip()
                        
                        categories = get_categories(item)
                        rating = get_rating(item)
                        relationships = [r.text for r in item.select("li.relationships a")]
                        # 抓取自由标签 (Freeform Tags / Additional Tags)
                        freeform_tags = [t.text for t in item.select("li.freeforms a")]

                        stats_dl = item.find("dl", class_="stats")
                        chapters_text = "1/1"
                        status = "Completed"
                        if stats_dl:
                            chap_dd = stats_dl.find("dd", class_="chapters")
                            if chap_dd:
                                chapters_text = chap_dd.text.strip()
                                if "/" in chapters_text:
                                    curr, total = chapters_text.split('/', 1)
                                    if total == "?" or curr != total:
                                        status = "In Progress"
                                    else:
                                        status = "Completed"
                        
                        status_span = h4.find("span", class_="status")
                        w_type = "Normal"
                        if status_span:
                            st_text = status_span.text.lower()
                            if "anonymous" in st_text: w_type = "Anonymous"
                            if "unrevealed" in st_text: w_type = "Unrevealed"

                        def gv(c): return parse_int(stats_dl.find("dd", class_=c).text) if stats_dl and stats_dl.find("dd", class_=c) else 0
                        
                        if not any(x['work_id'] == wid for x in work_list_skeleton):
                            work_list_skeleton.append({
                                "work_id": wid,
                                "title": title,
                                "url": link['href'],
                                "work_type": w_type,
                                "rating": rating,
                                "categories": categories,
                                "relationships": relationships,  # ✅ 补全关系
                                "freeform_tags": freeform_tags,  # ✅ 补全自由标签
                                "status": status,
                                "chapters_text": chapters_text,
                                "fandoms": [t.text for t in item.select("h5.fandoms a")],
                                "words": gv("words"),
                                "kudos": gv("kudos"),
                                "hits": gv("hits"),
                                "comments_count": gv("comments"),
                                "date_updated": item.find("p", class_="datetime").text.strip(),
                                "real_subs": stats_map.get(wid, {}).get("subs", 0),
                                "real_bookmarks": stats_map.get(wid, {}).get("bookmarks", 0),
                                "chapters_detail": [] 
                            })
                    page_num += 1
                    time.sleep(2)  # 👈 非常重要
            except Exception as e:
                print(f"   ⚠️ 扫描 {label} 出错: {e}")

        scan_list("works", "主页作品")
        scan_list("works/collected", "合集作品")
        print(f"   ✔ 共发现 {len(work_list_skeleton)} 篇作品")

        # ================= 4. 深度抓取 =================
        print("\n🕵️ [3/3] 深度抓取 (章节详情 & 评论树)...")
        
        final_works = []
        for w in tqdm(work_list_skeleton, desc="Processing"):
            try:
                # --- Step A: 抓取章节详情 (/navigate) ---
                # 【修改点】: 移除了对 "Unrevealed" 的过滤，让所有作品都尝试抓取 navigate
                # 因为作者本人有权限看到 Unrevealed 作品的章节列表
                
                nav_url = f"https://archiveofourown.org{w['url']}/navigate"
                page.goto(
                nav_url,
                timeout=60000,
                wait_until="domcontentloaded"
            )

                if page.locator("text='Proceed'").count() > 0: page.click("text='Proceed'")
                
                # 检查 URL 是否还在 navigate 页面 (单章作品会自动重定向回主页)
                if "/navigate" in page.url:
                    soup_nav = BeautifulSoup(page.content(), "html.parser")
                    chap_items = soup_nav.select("ol.chapter.index li")
                    
                    for idx, li in enumerate(chap_items, 1):
                        date_span = li.find("span", class_="datetime")
                        c_date = date_span.text.strip("()") if date_span else ""
                        c_link = li.find("a")
                        c_title = c_link.text.strip() if c_link else f"Chapter {idx}"
                        
                        w["chapters_detail"].append({
                            "chapter_index": idx,
                            "chapter_title": c_title,
                            "publish_date": c_date
                        })
                else:
                    # 如果重定向了，说明是单章 (或者极少见的特殊隐藏情况)，用更新日期兜底
                    w["chapters_detail"].append({
                        "chapter_index": 1,
                        "chapter_title": w['title'], # 单章作品没有章节名，用作品名
                        "publish_date": w['date_updated']
                    })
                
                # 如果 Unrevealed 抓取成功，chapters_detail 应该有 25 项了
                
                # --- Step B: 抓取全文与评论 ---
                full_url = f"https://archiveofourown.org{w['url']}?view_full_work=true&show_comments=true&view_adult=true"
                page.goto(full_url, timeout=60000)
                if page.locator("text='Proceed'").count() > 0: 
                    page.click("text='Proceed'")
                    page.wait_for_load_state("domcontentloaded")

                soup = BeautifulSoup(page.content(), "html.parser")

                # 补全首次发布时间
                if w["chapters_detail"]:
                    w["first_published"] = w["chapters_detail"][0]["publish_date"]
                else:
                    meta_published = soup.select_one("dl.work.meta.group dd.published")
                    w["first_published"] = meta_published.get_text().strip() if meta_published else w.get("date_updated", "")

                # 抓取 Kudos
                try:
                    if page.locator("#kudos_summary a:has-text('others')").count() > 0:
                        page.click("#kudos_summary a:has-text('others')")
                        page.wait_for_timeout(500)
                        soup = BeautifulSoup(page.content(), "html.parser")
                except: pass

                kudos_els = soup.select("#kudos a[href^='/users/']")
                w["kudos_givers"] = [k['href'].split("/")[-1] for k in kudos_els]

                # 抓取评论树
                comments_tree = get_recursive_comments(soup)
                w["comments_tree"] = comments_tree
                
                w["commenters"] = [
                    {"user": c["user"], "chapter_index": c["chapter_index"]}
                    for c in comments_tree
                ]

                final_works.append(w)
                time.sleep(1) 

            except Exception as e:
                print(f"❌ 错误《{w['title']}》: {e}")
                final_works.append(w) 

        # 5. 保存
        full_data["works"] = final_works
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(full_data, f, ensure_ascii=False, indent=2)

        print("\n" + "="*50)
        print(f"🎉 抓取完成！数据已保存至 {DATA_FILE}")
        print("="*50)
        context.close()

if __name__ == "__main__":
    main()