import json
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
import sys
import time

def slow_print(text, delay=0.25):
    print(text)
    time.sleep(delay)

DATA_FILE = "my_ao3_db_2025.json"


def wait_next(part_name: str = ""):
    out("\n" * 5)
    tip = f"\n『{part_name}』"
    out("Enter 以继续")
    try:
        input(tip)
    except KeyboardInterrupt:
        out("\n中断退出。")
        sys.exit(0)


def clear_screen():
    out("\n" * 1)


def load_data() -> Optional[Dict[str, Any]]:
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        out("❌ 找不到数据文件，请先运行 fetch_data.py")
        return None


def ask_yes_no(prompt: str, default: str = "n") -> bool:
    default = default.lower()
    hint = "Y/n" if default == "y" else "y/N"
    while True:
        ans = input(f"{prompt} ({hint})：").strip().lower()
        if not ans:
            ans = default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        out("请输入 y 或 n。")


def parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def safe_list(x) -> List:
    return x if isinstance(x, list) else []


def normalize_rel_tag(tag: str) -> str:
    if not isinstance(tag, str):
        return ""
    t = tag.strip()
    t = t.replace("／", "/").replace(" ", "")
    return t


output_lines: List[str] = []
def out(text: str = ""):
    slow_print(text)
    output_lines.append(text)



def collect_comment_authors_from_tree(tree: Any) -> List[str]:
    authors: List[str] = []

    def walk(node: Any):
        if isinstance(node, dict):
            v = node.get("user")
            if isinstance(v, str) and v.strip():
                authors.append(v.strip())

            for k in node.values():
                if isinstance(k, (dict, list)):
                    walk(k)

        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(tree)
    return authors


def title_list_preview(titles: List[str], max_show: int = 3) -> str:
    if not titles:
        return ""
    show = titles[:max_show]
    suffix = f" 等{len(titles)}篇" if len(titles) > max_show else ""
    return "、".join(show) + suffix


def format_titles_multiline(
    titles: List[str], indent: str = "    · ", max_lines: int = 6
) -> str:
    titles = [t for t in titles if t]
    titles_sorted = sorted(titles)
    if not titles_sorted:
        return ""

    shown = titles_sorted[:max_lines]
    lines = "\n".join(f"{indent}{t}" for t in shown)
    if len(titles_sorted) > max_lines:
        lines += f"\n{indent}……以及另外 {len(titles_sorted) - max_lines} 篇"
    return lines


def split_works(
    works: List[Dict[str, Any]], include_hidden: bool, include_anon: bool
):
    main_works = []
    anon_only = []
    hidden_only = []

    for w in works:
        wt = w.get("work_type")
        if wt == "Unrevealed":
            if include_hidden:
                main_works.append(w)
            else:
                hidden_only.append(w)
        elif wt == "Anonymous":
            if include_anon:
                main_works.append(w)
            else:
                anon_only.append(w)
        else:
            main_works.append(w)

    return main_works, anon_only, hidden_only


def top_work_by(key: str, works: List[Dict[str, Any]]):
    valid = [w for w in works if int(w.get(key, 0) or 0) > 0]
    if not valid:
        return None
    return max(valid, key=lambda w: int(w.get(key, 0) or 0))


def get_hottest_chapter(work: Dict[str, Any], author: str):
    counter = Counter()

    for c in safe_list(work.get("comments_tree")):
        user = c.get("user")
        if not user or user == author:
            continue

        idx = c.get("chapter_index")
        if idx is not None:
            counter[idx] += 1

    if not counter:
        return None

    idx, cnt = counter.most_common(1)[0]
    name = f"Chapter {idx}"
    return name, cnt


def main():
    data = load_data()
    if not data:
        return

    account = data.get("account", {})
    username = account.get("username", "Unknown")
    works = safe_list(data.get("works"))


    anon_works = [w for w in works if w.get("work_type") == "Anonymous"]
    hidden_works = [w for w in works if w.get("work_type") == "Unrevealed"]

    print("=" * 60)
    out(f"📊 AO3 年终写作回顾 · {username}")
    print("=" * 60)

    include_hidden = ask_yes_no("要把【隐藏作品（Unrevealed）】也算进主要统计吗？", default="y")
    include_anon = ask_yes_no("要把【匿名作品（Anonymous）】也算进主要统计吗？", default="y")

    public_works, anon_only, hidden_only = split_works(
        works, include_hidden=include_hidden, include_anon=include_anon
    )

    # finished_public = [w for w in public_works if w.get("status") == "Completed"]
    serial_public = [w for w in public_works if len(safe_list(w.get("chapters_detail"))) > 1]

    total_words = sum(int(w.get("words", 0) or 0) for w in public_works)
    real_words = int(total_words * 10 / 9)
    total_kudos = sum(int(w.get("kudos", 0) or 0) for w in public_works)
    total_hits = sum(int(w.get("hits", 0) or 0) for w in public_works)
    total_comments = sum(int(w.get("comments_count", 0) or 0) for w in public_works)

    total_subs = sum(int(w.get("real_subs", 0) or 0) for w in works)
    total_bookmarks = sum(int(w.get("real_bookmarks", 0) or 0) for w in works)

    first_pub_dates = [parse_date(w.get("first_published")) for w in public_works]
    first_pub_dates = [d for d in first_pub_dates if d]

    span_str = ""
    if first_pub_dates:
        d1, d2 = min(first_pub_dates), max(first_pub_dates)
        span_str = f"从 {d1.strftime('%Y-%m-%d')} 到 {d2.strftime('%Y-%m-%d')}。"


    

    wait_next("初始选项")
    clear_screen()

    out("\n\n【这一年你写了什么】")
    out(f"这一年你统计了 {len(public_works)} 篇作品，总字数 {total_words:,}，{span_str}")
    out(f"它们一共收到了 {total_kudos} 个赞、{total_comments} 条评论、{total_hits} 次点击。")
    out(f"此外你累计获得 {total_subs} 个订阅、{total_bookmarks} 个书签。")
    out("（ps：stats 里能看到私密书签/订阅数量哦。）")
    out("\n>> 读者们爱你！")
    out("\n\n** ps: AO3的字数统计没有计入中文标点，实际字数比这还多！")
    out(f"按1/10的标点符号计算，你足足写了 {real_words:,} 个字！")

    wait_next("最亮眼的是……？")
    clear_screen()

    out("\n\n【这一年最亮眼的作品】")

    top_kudos_work = top_work_by("kudos", public_works)
    top_bm_work = top_work_by("real_bookmarks", public_works)
    top_cmt_work = top_work_by("comments_count", public_works)

    if top_kudos_work:
        out(f"\n你收到最多赞的是：《{top_kudos_work.get('title')}》"
              f"（{top_kudos_work.get('kudos')} 个赞）")
        out("你火啦！")

    if top_bm_work:
        out(f"\n 被收藏最多的是《{top_bm_work.get('title')}》"
              f"（{top_bm_work.get('real_bookmarks')} 个书签）")
        out("嘿嘿，好吃不厌！")

    if top_cmt_work:
        out(f"\n 评论最多的是《{top_cmt_work.get('title')}》"
              f"（{top_cmt_work.get('comments_count')} 条评论）")
        out("这太幸福了！")

    wait_next("这一年写了什么")
    clear_screen()

    # 后续模块逻辑与你原来一致，未改文案
    # （篇幅原因这里不再重复解释，只是代码）

    # ……【后续模块完整保留，逻辑已与 JSON 对齐】……
    # 新增：分级（rating）分析
    rating_counts = Counter()
    for w in public_works:
        rating_counts[w.get("rating", "Unknown") or "Unknown"] += 1

    if rating_counts:
        out("\n\n【分级口味】")
        explicit_mature = rating_counts.get("Explicit", 0) + rating_counts.get("Mature", 0)
        safe_side = rating_counts.get("General Audiences", 0) + rating_counts.get("Teen And Up Audiences", 0)

        # 顺手把分布列出来（不挤成一坨）
        for r, c in rating_counts.most_common():
            out(f"  - {r}：{c} 篇")

        # 不搞太复杂：按占比给两三种话术
        if explicit_mature >= max(1, len(public_works) * 0.5):
            out("Explicit / Mature 的存在感相当强！\n")
            out("你这一路在高速公路狂飙啊！\n")
        elif safe_side >= max(1, len(public_works) * 0.6):
            out("你的分级很温和，更像是在认真写关系和故事。\n")
        else:
            out("你怎么什么都沾点，全能大神来的吧！\n")

        

    # 新增：Category 分析
    category_counts = Counter()
    for w in public_works:
        for c in safe_list(w.get("categories")):
            if isinstance(c, str) and c.strip():
                category_counts[c.strip()] += 1

    
    for k, v in category_counts.most_common():
            out(f"  - {k}：{v} 篇")
    if category_counts:
        out("你的品味分布：")
        mm = category_counts.get("M/M", 0)
        ff = category_counts.get("F/F", 0)
        fm = category_counts.get("F/M", 0)
        dominant = False
        if mm >= max(1, int(len(public_works) * 0.8)):
            out("哇，你真的很专注男同。")
            out("\n>> 男的和男的99！")
            dominant = True
        if ff >= max(1, int(len(public_works) * 0.8)):
            out("哇，你真的很专注女同。")
            out("\n>> 女的和女的99！")
            dominant = True
        if fm >= max(1, int(len(public_works) * 0.8)):
            out("哇，你真的很专注BG/GB。")
            out("\n>> 此男此女乃天作之合！")
            dominant = True
        if not dominant:
            out("\n>> 你的口味真多元！高雅人士！")
        

    # 模块 2：写作节奏（按章节发布时间）
    update_dates: List[datetime] = []
    for w in public_works:
        for c in safe_list(w.get("chapters_detail")):
            dt = parse_date(c.get("publish_date"))
            if dt:
                update_dates.append(dt)

    out("\n\n【你的更新节奏】")
    if not update_dates:
        out("啊哦，出了点小问题……更新日期走丢了。")
    else:
        update_dates.sort()
        month_counts = Counter(d.strftime("%Y-%m") for d in update_dates)
        weekday_counts = Counter(d.weekday() for d in update_dates)
        weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}

        peak_month, peak_cnt = month_counts.most_common(1)[0]
        peak_day, day_cnt = weekday_counts.most_common(1)[0]
        out(f"你更新最集中的月份是 {peak_month}，一共更新了 {peak_cnt} 次。")
        out(f"你最常在 {weekday_map.get(peak_day, '某一天')} 更新（{day_cnt} 次）。")

        # 最长空档（按章节发布时间计算）
        gaps = []
        for i in range(1, len(update_dates)):
            gaps.append((update_dates[i] - update_dates[i - 1]).days)

        if gaps:
            longest_gap = max(gaps)
            out(f"\n按章节发布时间算，你这一年最长的一次“沉默期”是 {longest_gap} 天。")
            if longest_gap < 30:
                out("保持月更啊，这也太勤快了！女神！")
            else:
                out("女神不要走……我们想你……")


    # 模块 3：连载与“连载中更新其他篇目”
    if serial_public:
        wait_next("连载时刻")
        clear_screen()
        out("\n\n【当你在连载时】")
        for w in serial_public:
            chapters = safe_list(w.get("chapters_detail"))
            start = parse_date(chapters[0].get("publish_date")) if chapters else None
            end = parse_date(chapters[-1].get("publish_date")) if chapters else None
            if not start or not end:
                continue

            span_days = (end - start).days
            avg_speed = span_days / len(chapters) if len(chapters) else 0

            overlapping_titles = []
            for other in public_works:
                if other.get("work_id") == w.get("work_id"):
                    continue
                pub = parse_date(other.get("first_published"))
                if pub and start <= pub <= end:
                    overlapping_titles.append(other.get("title", "（无标题）"))

            # 判断状态，调整措辞
            status_text = "完结" if w.get("status") == "Completed" else "最近一更"
            out(f"\n《{w.get('title','（无标题）')}》从开更到{status_text}历时 {span_days} 天，平均约 {avg_speed:.1f} 天更新一章。")
            subs = int(w.get("real_subs", 0) or 0)
            bms = int(w.get("real_bookmarks", 0) or 0)

            if subs or bms:
                out(f"这篇连载累计收获了 {subs} 个订阅、{bms} 个书签。")
            else:
                out("这是一篇安静但被认真读完的连载。")
            hot = get_hottest_chapter(w, username)
            if hot:
                chapter, count = hot
                out(f"其中讨论最热烈的是 {chapter}，收获了 {count} 条评论！噢耶！")


            if overlapping_titles:
                sample = title_list_preview(overlapping_titles, max_show=3)
                out(f"\n连载期间,你还同时发布了 {len(overlapping_titles)} 篇其他作品（比如 {sample}）。")
                out("\n>> 真是精力旺盛啊！教程哪里领？")
            else:
                out("\n>> 你总是专心扑在自己的连载写作上，太伟大了！")
                out("读者们都泪流满面了！")
            wait_next(" >>> ")
            clear_screen()
            

    # # === 插入位置：在 top_cmt_work 的 if 块之后 ===
    
    # # 1. 汇总所有属于系列的作品
    # series_map = defaultdict(list)
    # for w in public_works:
    #     s_name = w.get("series_name")
    #     if s_name:
    #         series_map[s_name].append(w)

    # if series_map:
    #     wait_next("series")
    #     clear_screen()

    #     out("\n\n【你的系列宇宙】")
    #     out(f"这一年，你建设了 {len(series_map)} 个series！")
    #     for s_name, s_works in series_map.items():
    #         # 按 series_part 排序 (Part 1, Part 2...)
    #         s_works.sort(key=lambda x: x.get("series_part") or "")
    #         titles = [f"《{w['title']}》({w.get('series_part', '??')})" for w in s_works]
    #         out(f"\n· 系列《{s_name}》：")
    #         out(f"  包含 {len(titles)} 篇作品：{' 、 '.join(titles)}")
        
    #     # 如果 fetch 阶段抓到了 series_list 的汇总数据
    #     all_series_stats = safe_list(data.get("series_list"))
    #     if all_series_stats:
    #         top_s = max(all_series_stats, key=lambda x: x.get("bookmarks", 0))
    #         out(f"\n在你的所有系列中，最受瞩目的是《{top_s['title']}》，")
    #         out(f"它已累计获得了 {top_s['bookmarks']} 个bookmark！噢耶！")

    # 合集真的适合统计吗 还是先不统计了谢谢！
    # out("\n\n【合集印记】")
    # # 2. 统计合集收录情况
    # all_collections = []
    # for w in public_works:
    #     all_collections.extend(safe_list(w.get("collections_info")))
    
    # if not all_collections:
    #     out("这一年的作品暂时还没有被收录进任何公开合集中。")
    # else:
    #     col_counts = Counter(all_collections)
    #     out(f"你的作品这一年出现在了 {len(col_counts)} 个不同的合集中。")
    #     out("被收录次数最多的合集是：")
    #     for name, count in col_counts.most_common(3):
    #         out(f"  - {name} ({count} 次)")
    #     out("\n>> 谢谢这些合集主，把你的文字妥善珍藏。")


    # 模块 4：互动密度（评论/赞）——你要求用“每个赞对应多少评论”
    # wait_next(" 讨论密度 ")
    # clear_screen()
    
    out("\n\n【讨论密度】")
    
    if total_kudos <= 0:
        out("啊哦，出了点小问题……讨论密度走丢了。")
    else:
        ratio = total_comments / total_kudos
        out(f"平均来看，每赞对应 {ratio:.2f} 条评论。")
        out(f"对长篇连载，赞评比比kudos更反馈你的优秀哦~")
    wait_next("♪谁是我最爱的人")
    clear_screen()

    # 模块 5：读者榜（Kudos / Comments）
    # 5.1 Kudos 榜：统计“点过你多少篇作品”
    kudos_user_to_titles: Dict[str, Set[str]] = defaultdict(set)
    for w in works:
        wt = w.get("work_type")

        if wt == "Unrevealed" and not include_hidden:
            continue
        if wt == "Anonymous" and not include_anon:
            continue

        title = w.get("title", "（无标题）")
        for u in safe_list(w.get("kudos_givers")):
            if isinstance(u, str) and u.strip():
                kudos_user_to_titles[u.strip()].add(title)


    # 5.2 Comments 榜：优先 comments_tree
    comment_user_to_titles: Dict[str, Set[str]] = defaultdict(set)
    for w in works:
        wt = w.get("work_type")

        if wt == "Unrevealed" and not include_hidden:
            continue
        if wt == "Anonymous" and not include_anon:
            continue

        title = w.get("title", "（无标题）")
        tree = w.get("comments_tree")
        authors = collect_comment_authors_from_tree(tree) if tree else []

        for a in authors:
            if a and a not in ("Guest", username):
                comment_user_to_titles[a].add(title)


    out("\n\n【现在开始播放：《爱我的人 谢谢你》-薛之谦】")
    out("♪登登等等，读者们重磅登场！")


    wait_next("kudos英雄榜")
    clear_screen()


    if kudos_user_to_titles:
        top_kudos = sorted(kudos_user_to_titles.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        out("\n给你点赞最多的人：")
        for user, titles in top_kudos:
            titles_list = sorted(list(titles))
            out(f"\n- {user}（留下 {len(titles)} 个kudos！）")
            out(format_titles_multiline(titles_list, indent="    · ", max_lines=6))
    else:
        out("\n啊哦，出了点小问题……点赞榜暂时无法生成。")
    
    wait_next("COMMENT英雄榜")
    clear_screen()

    if comment_user_to_titles:
        top_comments = sorted(comment_user_to_titles.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        out("\n\n最常在你评论区出现的人：")
        for user, titles in top_comments:
            titles_list = sorted(list(titles))
            out(f"\n- {user}（带来了 {len(titles)} 个大评论！么么哒！）")
            out(format_titles_multiline(titles_list, indent="    · ", max_lines=6))
    else:
        out("\n\n啊哦，出了点小问题……评论榜暂时无法生成。")
        out("（抓不到，根本抓不到！我的代码又崩溃了！）")
    wait_next("你 的 世 界")
    clear_screen()

    # 模块 6：题材与标签倾向（fandom / relationship / freeform）
    fandom_counts = Counter()
    rel_counts_raw = Counter()
    rel_counts_norm = Counter()
    freeform_counts = Counter()

    for w in public_works:
        for f in safe_list(w.get("fandoms")):
            if isinstance(f, str) and f.strip():
                fandom_counts[f.strip()] += 1

        for r in safe_list(w.get("relationships")):
            if isinstance(r, str) and r.strip():
                rel_counts_raw[r.strip()] += 1
                rel_counts_norm[normalize_rel_tag(r)] += 1

        for t in safe_list(w.get("freeform_tags")):
            if isinstance(t, str) and t.strip():
                freeform_counts[t.strip()] += 1

    if fandom_counts:
        top_fandom, cnt = fandom_counts.most_common(1)[0]
        out("\n\n【你常驻的世界】")
        out(f"这一年你主要写的是 {top_fandom}（出现在 {cnt} 篇作品里）。")

    if rel_counts_raw:
        out("\n\n【你写的关系走向】")
        total_rel_tags = sum(rel_counts_raw.values())
        unique_rel_tags = len(rel_counts_raw)

        if unique_rel_tags == total_rel_tags:
            out("玩得真花！你几乎没有写过重复的关系/产品！")
        else:
            common = rel_counts_raw.most_common(5)
            out("长情的作者啊，你最爱吃这些产品：")
            for r, c in common:
                out(f"  - {r}（{c} 次）")

        # 你要的解释：可能重复
        
        out("\n因为 AO3 的 CP/关系标签存在别名、顺序差异、中英混写、全角斜杠等原因，")
        out("同一个关系可能会出现“重复”的条目，滑跪TAT")

        wait_next(" 高雅品味 ")
        clear_screen()

    if freeform_counts:
        out("\n\n【你偏爱的主题与口味】")
        if all(c == 1 for c in freeform_counts.values()):
            out("你这一年的 tag 几乎没有重复，真是多点开花啊！每一篇都在朝新方向狂奔！")
        else:
            repeated = [(t, c) for t, c in freeform_counts.items() if c > 1]
            repeated.sort(key=lambda x: x[1], reverse=True)

            out("你明显偏好这些 tag：")
            for t, c in repeated[:8]:
                out(f"  - {t}（{c} 次）")

            once_only = [t for t, c in freeform_counts.items() if c == 1]
            once_only.sort()
            if once_only:
                sample = title_list_preview(once_only, max_show=3)
                out("\n除此之外，你也写了不少别的主题，真是多点开花啊！")
                out(f"比如：{sample}")
    wait_next("how will you be next ..?")
    clear_screen()

    # 你要的：如果不纳入匿名/隐藏，单独开小节做分析
    if anon_works:
        out("\n\n【嘘，偷偷的……】")
        out(f"你这一年还有 {len(anon_works)} 篇匿名作品~~")
        titles = [w.get("title", "（无标题）") for w in anon_works]
        out(format_titles_multiline(titles, indent="    · ", max_lines=10))

        anon_words = sum(int(w.get("words", 0) or 0) for w in anon_works)
        anon_kudos = sum(int(w.get("kudos", 0) or 0) for w in anon_works)
        anon_hits = sum(int(w.get("hits", 0) or 0) for w in anon_works)
        anon_comments = sum(int(w.get("comments_count", 0) or 0) for w in anon_works)
        out(f"\n匿名作品合计：{anon_words:,} 字，{anon_kudos} 赞，{anon_comments} 评论，{anon_hits} 点击。")
        out(f">> 达成成就：面具之下，是更美的面具~")

    if hidden_works:
        out("\n\n【被隐藏的……】")
        out(f"你这一年有 {len(hidden_works)} 篇隐藏作品~~")
        titles = [w.get("title", "（无标题）") for w in hidden_works]
        out(format_titles_multiline(titles, indent="    · ", max_lines=10))

        hidden_words = sum(int(w.get("words", 0) or 0) for w in hidden_works)
        hidden_kudos = sum(int(w.get("kudos", 0) or 0) for w in hidden_works)
        hidden_hits = sum(int(w.get("hits", 0) or 0) for w in hidden_works)
        hidden_comments = sum(int(w.get("comments_count", 0) or 0) for w in hidden_works)
        out(f"\n隐藏作品合计：{hidden_words:,} 字，{hidden_kudos} 赞，{hidden_comments} 评论，{hidden_hits} 点击。")
        out(f">> 哪天我们会与它们相见呢？")
        wait_next("how will you be next..?")
    out("\n报告结束，谢谢你的存在。")
    print(f"最后的最后……")
    save_txt = ask_yes_no("要把这份年终报告保存成 txt 文件吗？", default="y")
    if save_txt:
        filename = f"AO3_Year_Report_{username}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines))
        print(f"\n已保存为：{filename}")


    out("\n" + "=" * 60)
    


if __name__ == "__main__":
    main()
