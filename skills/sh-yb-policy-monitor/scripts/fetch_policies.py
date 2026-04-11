"""上海医保局政策监控 - 自动获取最新政策文件

用法：
    python fetch_policies.py              # 检查昨天发布的内容
    python fetch_policies.py --date 2026-03-19  # 检查指定日期
    python fetch_policies.py --days 3     # 检查最近3天

依赖：pip install requests beautifulsoup4
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DEFAULT_SAVE_SUBDIR = Path("data") / "sh-yb-policies"
BASE_URL = "https://ybj.sh.gov.cn"

CHANNELS = [
    {"id": "ybdt", "name": "医保动态", "url": f"{BASE_URL}/ybdt/index.html"},
    {"id": "zxzc", "name": "最新政策", "url": f"{BASE_URL}/zxzc/index.html"},
    {"id": "gsgg", "name": "公示公告", "url": f"{BASE_URL}/gsgg/index.html"},
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

DATE_PATTERNS = [
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"(\d{4})/(\d{2})/(\d{2})"),
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
]


def sanitize_filename(title: str, max_len: int = 20) -> str:
    cleaned = title[:max_len]
    cleaned = re.sub(r'[\\/:*?"<>|【】\s]+', "_", cleaned)
    return cleaned.strip("_")


def normalize_date(text: str) -> str | None:
    """Extract and normalize date from text to YYYY-MM-DD format."""
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            y, m, d = match.group(1), match.group(2), match.group(3)
            return f"{y}-{int(m):02d}-{int(d):02d}"
    return None


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.encoding = "utf-8"
    return resp.text


def parse_listing(html: str, channel_url: str) -> list[dict]:
    """Extract articles with title, date, and URL from a listing page."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen_urls = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        title = a_tag.get_text(strip=True)

        if not title or len(title) < 4:
            continue
        if href in ("#", "/", "javascript:void(0)"):
            continue
        if href.endswith("index.html") or href.endswith("index.htm"):
            continue

        full_url = urljoin(channel_url, href)
        if full_url in seen_urls or BASE_URL not in full_url:
            continue

        date_str = None

        parent = a_tag.find_parent(["li", "div", "tr", "dd"])
        if parent:
            parent_text = parent.get_text()
            date_str = normalize_date(parent_text)

        if not date_str:
            next_sib = a_tag.find_next_sibling()
            if next_sib:
                date_str = normalize_date(next_sib.get_text())

        if not date_str:
            url_match = re.search(r"/(\d{4})(\d{2})(\d{2})/", href)
            if url_match:
                y, m, d = url_match.group(1), url_match.group(2), url_match.group(3)
                date_str = f"{y}-{m}-{d}"

        if date_str:
            articles.append({"title": title, "date": date_str, "url": full_url})
            seen_urls.add(full_url)

    return articles


def fetch_article_content(url: str) -> str:
    """Fetch article detail page and extract main content as text."""
    try:
        html = fetch_page(url)
    except Exception as e:
        return f"（获取正文失败：{e}）"

    soup = BeautifulSoup(html, "html.parser")

    content_selectors = [
        ("div", {"class": re.compile(r"article[-_]?content|art[-_]?con|text[-_]?content|TRS_Editor", re.I)}),
        ("div", {"class": re.compile(r"content|article|detail|body|text|main", re.I)}),
        ("div", {"id": re.compile(r"content|article|detail|body|text", re.I)}),
        ("article", {}),
    ]

    content_div = None
    for tag_name, attrs in content_selectors:
        content_div = soup.find(tag_name, attrs)
        if content_div:
            break

    if content_div:
        for tag in content_div.find_all(["script", "style", "nav", "footer"]):
            tag.decompose()
        return content_div.get_text(separator="\n", strip=True)

    paragraphs = soup.find_all("p")
    if paragraphs:
        texts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
        if texts:
            return "\n\n".join(texts)

    return "（未能提取正文内容，请访问原文链接查看）"


def default_save_dir_from_script(script_path: str | Path | None = None) -> Path:
    resolved_script = Path(script_path or __file__).resolve()
    skills_ancestors = [parent for parent in resolved_script.parents if parent.name == "skills"]
    if skills_ancestors:
        return (skills_ancestors[-1].parent / DEFAULT_SAVE_SUBDIR).resolve()
    return (resolved_script.parent / DEFAULT_SAVE_SUBDIR).resolve()


def resolve_save_dir(explicit_save_dir: str | None = None) -> Path:
    if explicit_save_dir:
        return Path(explicit_save_dir).expanduser().resolve()
    env_override = os.environ.get("SH_YB_POLICY_SAVE_DIR", "").strip()
    if env_override:
        return Path(env_override).expanduser().resolve()
    return default_save_dir_from_script()


def save_article(article: dict, channel: dict, content: str, save_dir: Path | None = None) -> Path | None:
    """Save article as markdown. Returns filepath if saved, None if duplicate."""
    target_dir = save_dir or default_save_dir_from_script()
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{article['date']}_{channel['id']}_{sanitize_filename(article['title'])}.md"
    filepath = target_dir / filename

    if filepath.exists():
        return None

    md = (
        f"# {article['title']}\n\n"
        f"- **来源**：上海市医疗保障局\n"
        f"- **栏目**：{channel['name']}\n"
        f"- **发布日期**：{article['date']}\n"
        f"- **原文链接**：{article['url']}\n\n"
        f"---\n\n"
        f"{content}\n"
    )
    filepath.write_text(md, encoding="utf-8")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="上海医保局政策监控")
    parser.add_argument("--date", help="检查指定日期 (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=1, help="检查最近N天 (默认1=昨天)")
    parser.add_argument("--save-dir", help="输出目录，默认使用脚本内置路径或 SH_YB_POLICY_SAVE_DIR")
    args = parser.parse_args()
    save_dir = resolve_save_dir(args.save_dir)

    if args.date:
        target_dates = {args.date}
    else:
        today = datetime.now()
        target_dates = {
            (today - timedelta(days=i + 1)).strftime("%Y-%m-%d")
            for i in range(args.days)
        }

    target_dates_str = ", ".join(sorted(target_dates))
    print(f"检查日期：{target_dates_str}")
    print(f"保存路径：{save_dir}")
    print("=" * 60)

    all_results = []
    failed_channels = 0

    for channel in CHANNELS:
        print(f"\n正在检查【{channel['name']}】({channel['url']})")
        try:
            html = fetch_page(channel["url"])
            articles = parse_listing(html, channel["url"])
            matched = [a for a in articles if a["date"] in target_dates]

            if not matched:
                print(f"  → {target_dates_str} 无新发布内容")
                continue

            print(f"  → 找到 {len(matched)} 篇新文章")

            for article in matched:
                print(f"  ● {article['title']} ({article['date']})")

                content = fetch_article_content(article["url"])
                saved_path = save_article(article, channel, content, save_dir=save_dir)

                result = {
                    "channel": channel["name"],
                    "channel_id": channel["id"],
                    "title": article["title"],
                    "date": article["date"],
                    "url": article["url"],
                    "saved": str(saved_path) if saved_path else "已存在，跳过",
                    "content_preview": content[:300] + "..." if len(content) > 300 else content,
                }
                all_results.append(result)

                if saved_path:
                    print(f"    → 已保存：{saved_path.name}")
                else:
                    print(f"    → 已存在，跳过")

        except Exception as e:
            failed_channels += 1
            print(f"  ✗ 获取失败：{e}", file=sys.stderr)

    print("\n" + "=" * 60)

    if all_results:
        print(f"\n=== 摘要：共获取 {len(all_results)} 篇新文件 ===\n")
        for r in all_results:
            print(f"【{r['channel']}】{r['title']}")
            print(f"  日期：{r['date']}")
            print(f"  链接：{r['url']}")
            print(f"  状态：{r['saved']}")
            print(f"  预览：{r['content_preview']}")
            print()
    else:
        print(f"\n{target_dates_str} 三个栏目均无新发布内容。")

    if failed_channels:
        print(f"\n本次有 {failed_channels} 个栏目获取失败。", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
