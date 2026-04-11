"""WeChat article fetch + monitor pipeline for hospital-claw.

This script adapts the lightweight article-to-Markdown flow into the repo's
storage, classification, and reporting conventions for the daily WeChat monitor.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

DEFAULT_OUTPUT_DIR = Path("docs") / "医院材料学习" / "公众号每日监测"
REPORTS_DIRNAME = "_reports"
IMAGES_DIRNAME = "images"
INVALID_LINK_PREFIXES = ("javascript:", "#")
SHANGHAI_TZ = timezone(timedelta(hours=8))

WECHAT_NOISE_PATTERNS = [
    re.compile(r"^预览时标签不可点$"),
    re.compile(r"^继续滑动看下一个$"),
    re.compile(r"^微信扫一扫关注该公众号$"),
    re.compile(r"^轻触阅读原文$"),
    re.compile(r"^以下文章来源于.*$"),
    re.compile(r"^喜欢此内容的人还喜欢$"),
    re.compile(r"^作者[:：].*$"),
]

P0_KEYWORDS = [
    "医保局令",
    "实施细则",
    "目录调整",
    "飞行检查",
    "突击检查",
    "进驻",
    "重点科室",
    "骗保",
    "罚款",
    "取消定点",
    "移交公安",
    "项目价格",
    "加收",
    "编码调整",
    "取消收费",
]
P1_KEYWORDS = [
    "针刺合规",
    "艾灸限制",
    "推拿医保",
    "拔罐禁忌",
    "病历书写",
    "证型必填",
    "四单一致",
    "复制粘贴",
    "拒付",
    "申报",
    "审核",
    "扣款",
    "DRG",
    "DIP",
    "病种付费",
    "分值",
    "盈亏分析",
]
P2_KEYWORDS = [
    "中医馆月营收",
    "门诊量增长",
    "单店模型",
    "医师招聘",
    "绩效考核",
    "团队搭建",
    "私域流量",
    "复诊率",
    "转介绍",
    "HIS系统",
    "AI预问诊",
    "智能导诊",
]
P3_KEYWORDS = [
    "市场规模",
    "竞争格局",
    "继续教育",
    "培训",
    "设备",
    "耗材",
    "集采",
    "行业数据",
    "学术",
]
P4_KEYWORDS = [
    "养生",
    "食疗",
    "广告",
    "推广",
    "软文",
    "优惠",
]


@dataclass
class ArticleBundle:
    title: str
    account_name: str
    publish_time: str
    source_url: str
    markdown_body: str
    cleaned_html: str = ""
    priority: str = "P3"
    matched_keywords: list[str] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)


class ImageDownloader:
    """Download article images into the current article bundle."""

    def __init__(self, article_dir: Path, timeout: int = 30) -> None:
        self.article_dir = article_dir
        self.timeout = timeout
        self.count = 0
        self.images_dir = article_dir / IMAGES_DIRNAME
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def download(self, source: str) -> str | None:
        source = html.unescape((source or "").strip()).split("#", 1)[0]
        if not source or source.startswith("data:"):
            return None
        if source.startswith("//"):
            source = f"https:{source}"

        self.count += 1
        filename = f"img_{self.count:02d}{detect_image_extension(source)}"
        target = self.images_dir / filename

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if "mmbiz.qpic.cn" in source or "weixin" in source:
            headers["Referer"] = "https://mp.weixin.qq.com/"
            headers["Origin"] = "https://mp.weixin.qq.com"

        try:
            response = requests.get(source, headers=headers, timeout=self.timeout, stream=True)
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
        except requests.RequestException:
            target.unlink(missing_ok=True)
            return None

        if target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            return None

        return f"{IMAGES_DIRNAME}/{filename}"


def normalize_wechat_url(raw_url: str) -> str:
    value = html.unescape((raw_url or "").strip())
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1].strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    value = re.sub(r"\\+([:/&?=#%])", r"\1", value)
    if value.startswith("mp.weixin.qq.com/") or value.startswith("//mp.weixin.qq.com/"):
        value = "https://" + value.lstrip("/")

    parsed = urlparse(value)
    if (parsed.hostname or "").lower() == "mp.weixin.qq.com":
        value = urlunparse(
            ("https", "mp.weixin.qq.com", parsed.path, parsed.params, parsed.query, parsed.fragment)
        )
    return value


def validate_wechat_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and hostname in {
        "mp.weixin.qq.com",
        "weixin.qq.com",
    }


def normalize_inline_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def sanitize_path_segment(value: str, max_length: int = 80) -> str:
    value = normalize_inline_text(value)
    value = re.sub(r'[<>:"/\\|?*]', "_", value)
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value).strip("._ ")
    return (value[:max_length] or "untitled").strip("._ ") or "untitled"


def detect_image_extension(source: str) -> str:
    parsed = urlparse(source)
    query = parsed.query.lower()
    for fmt, extension in [
        ("png", ".png"),
        ("gif", ".gif"),
        ("webp", ".webp"),
        ("jpeg", ".jpg"),
        ("jpg", ".jpg"),
    ]:
        if f"wx_fmt={fmt}" in query:
            return extension

    lower_path = parsed.path.lower()
    for extension in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        if lower_path.endswith(extension):
            return ".jpg" if extension == ".jpeg" else extension
    return ".jpg"


def format_timestamp(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def extract_publish_time(source_html: str, soup: BeautifulSoup) -> str:
    selectors = [
        "#publish_time",
        ".publish_time",
        "meta[property='article:published_time']",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            if node.name == "meta":
                content = normalize_inline_text(node.get("content", ""))
            else:
                content = normalize_inline_text(node.get_text(" ", strip=True))
            if content:
                return content

    for pattern in [
        r'create_time\s*[:=]\s*["\']?(\d{10})["\']?',
        r'publish_time\s*[:=]\s*["\']?(\d{10})["\']?',
    ]:
        match = re.search(pattern, source_html, re.IGNORECASE)
        if match:
            return format_timestamp(int(match.group(1)))

    return ""


def append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def classify_article(title: str, body_text: str, account_name: str = "") -> dict[str, Any]:
    del body_text, account_name
    search_text = normalize_inline_text(title)
    matched_keywords: list[str] = []

    def contains(keyword: str) -> bool:
        return keyword in search_text

    def contains_all(*keywords: str) -> bool:
        return all(contains(keyword) for keyword in keywords)

    def contains_any(keywords: Sequence[str]) -> bool:
        return any(contains(keyword) for keyword in keywords)

    if contains_all("医保局", "令"):
        append_unique(matched_keywords, "医保局令")
    if contains("4月1日"):
        append_unique(matched_keywords, "4月1日施行")
    if contains_all("飞检", "启动"):
        append_unique(matched_keywords, "飞检启动")
    if contains_any(["骗保", "处罚", "罚款", "取消定点"]) and contains_any(["中医", "门诊", "诊所"]):
        append_unique(matched_keywords, "警示案例")
    if matched_keywords:
        return {
            "priority": "P0",
            "matched_keywords": matched_keywords,
            "matched_rule": "automatic_p0",
        }

    if contains_any(P0_KEYWORDS):
        for keyword in P0_KEYWORDS:
            if contains(keyword):
                append_unique(matched_keywords, keyword)
        return {
            "priority": "P0",
            "matched_keywords": matched_keywords,
            "matched_rule": "keyword_p0",
        }

    if contains_any(["针刺", "艾灸", "推拿"]) and contains_any(["医保", "合规", "收费"]):
        for keyword in ["针刺", "艾灸", "推拿", "医保", "合规", "收费"]:
            if contains(keyword):
                append_unique(matched_keywords, keyword)
        return {
            "priority": "P1",
            "matched_keywords": matched_keywords,
            "matched_rule": "automatic_p1",
        }

    if contains_any(P1_KEYWORDS):
        for keyword in P1_KEYWORDS:
            if contains(keyword):
                append_unique(matched_keywords, keyword)
        return {
            "priority": "P1",
            "matched_keywords": matched_keywords,
            "matched_rule": "keyword_p1",
        }

    if contains_any(["中医馆", "门诊"]) and contains_any(["营收", "运营", "案例"]):
        for keyword in ["中医馆", "门诊", "营收", "运营", "案例"]:
            if contains(keyword):
                append_unique(matched_keywords, keyword)
        return {
            "priority": "P2",
            "matched_keywords": matched_keywords,
            "matched_rule": "automatic_p2",
        }

    if contains_any(P2_KEYWORDS):
        for keyword in P2_KEYWORDS:
            if contains(keyword):
                append_unique(matched_keywords, keyword)
        return {
            "priority": "P2",
            "matched_keywords": matched_keywords,
            "matched_rule": "keyword_p2",
        }

    if contains_any(P4_KEYWORDS):
        for keyword in P4_KEYWORDS:
            if contains(keyword):
                append_unique(matched_keywords, keyword)
        return {
            "priority": "P4",
            "matched_keywords": matched_keywords,
            "matched_rule": "keyword_p4",
        }

    if contains_any(P3_KEYWORDS):
        for keyword in P3_KEYWORDS:
            if contains(keyword):
                append_unique(matched_keywords, keyword)
        return {
            "priority": "P3",
            "matched_keywords": matched_keywords,
            "matched_rule": "keyword_p3",
        }

    return {"priority": "P3", "matched_keywords": [], "matched_rule": "default_archive"}


def publish_date_string(publish_time: str) -> str:
    normalized = normalize_inline_text(publish_time)
    if not normalized:
        return datetime.now(tz=SHANGHAI_TZ).strftime("%Y-%m-%d")
    match = re.match(r"(\d{4}-\d{2}-\d{2})", normalized)
    if match:
        return match.group(1)
    match = re.search(r"(\d{4})[/.年](\d{1,2})[/.月](\d{1,2})", normalized)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    if re.fullmatch(r"\d{10}", normalized):
        return format_timestamp(int(normalized))[:10]
    return datetime.now(tz=SHANGHAI_TZ).strftime("%Y-%m-%d")


def build_article_output_dir(
    output_root: Path,
    publish_time: str,
    account_name: str,
    title: str,
) -> Path:
    date_dir = output_root / publish_date_string(publish_time)
    account_dir = date_dir / sanitize_path_segment(account_name or "未知公众号", max_length=60)
    account_dir.mkdir(parents=True, exist_ok=True)

    next_number = 1
    for child in account_dir.iterdir():
        if not child.is_dir():
            continue
        match = re.match(r"^(\d+)_", child.name)
        if match:
            next_number = max(next_number, int(match.group(1)) + 1)

    folder_name = f"{next_number:02d}_{sanitize_path_segment(title, max_length=72)}"
    article_dir = account_dir / folder_name
    article_dir.mkdir(parents=True, exist_ok=True)
    return article_dir


def extract_summary_lines(markdown_body: str, limit: int = 3) -> list[str]:
    lines: list[str] = []
    in_code_block = False

    for raw_line in markdown_body.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or not stripped:
            continue
        if stripped.startswith(("#", "![", ">")):
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        stripped = normalize_inline_text(stripped)
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) >= limit:
            break

    return lines


def extract_article_parts(source_html: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(source_html, "html.parser")

    title = ""
    for selector in ["#activity-name", "meta[property='og:title']", "title"]:
        node = soup.select_one(selector)
        if not node:
            continue
        if node.name == "meta":
            title = normalize_inline_text(node.get("content", ""))
        else:
            title = normalize_inline_text(node.get_text(" ", strip=True))
        if title:
            break
    if not title:
        title = "未命名文章"

    account_name = ""
    for selector in ["#js_name", ".profile_nickname", "meta[name='author']"]:
        node = soup.select_one(selector)
        if not node:
            continue
        if node.name == "meta":
            account_name = normalize_inline_text(node.get("content", ""))
        else:
            account_name = normalize_inline_text(node.get_text(" ", strip=True))
        if account_name:
            break

    content_root = soup.select_one("#js_content")
    if content_root is None:
        raise ValueError("Could not locate WeChat article body (#js_content)")

    cleaned_root = BeautifulSoup(str(content_root), "html.parser")
    working_root = cleaned_root.select_one("#js_content")
    if working_root is None:
        working_root = cleaned_root

    for comment in working_root.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for selector in [
        "script",
        "style",
        "noscript",
        "iframe",
        "#js_pc_qr_code",
        ".qr_code_pc",
        ".reward_area",
        ".js_ad_link",
        ".weui_media_box",
        ".js_product_container",
        ".original_primary_card_tips",
    ]:
        for node in working_root.select(selector):
            node.decompose()

    for code_wrap in working_root.select(".code-snippet__fix"):
        replacement = cleaned_root.new_tag("pre")
        lang_node = code_wrap.select_one("pre[data-lang]")
        if lang_node and lang_node.get("data-lang"):
            replacement["data-lang"] = lang_node["data-lang"]

        lines: list[str] = []
        for code_node in code_wrap.find_all("code"):
            parent_classes = " ".join(code_node.parent.get("class", [])) if isinstance(code_node.parent, Tag) else ""
            if "code-snippet__line-index" in parent_classes:
                continue
            text = code_node.get_text()
            if text:
                lines.append(text)

        if not lines:
            fallback = code_wrap.get_text("\n")
            if fallback:
                lines.append(fallback)

        replacement.string = "\n".join(line.rstrip() for line in lines).strip("\n")
        code_wrap.replace_with(replacement)

    for img in working_root.find_all("img"):
        source = img.get("data-src") or img.get("data-original") or img.get("src") or ""
        source = html.unescape(source)
        if source:
            img["src"] = source

    publish_time = extract_publish_time(source_html, soup)
    body_text = normalize_inline_text(working_root.get_text("\n"))

    return {
        "title": title,
        "account_name": account_name,
        "publish_time": publish_time,
        "source_url": source_url,
        "content_root": working_root,
        "cleaned_html": str(working_root),
        "body_text": body_text,
    }


def render_children(node: Tag, downloader: ImageDownloader, base_url: str) -> str:
    return "".join(render_node(child, downloader, base_url, 0) for child in node.children)


def render_node(node: Any, downloader: ImageDownloader, base_url: str, list_level: int) -> str:
    if isinstance(node, NavigableString):
        return normalize_inline_text(str(node))
    if not isinstance(node, Tag):
        return ""

    name = node.name.lower()

    if name in {"script", "style", "noscript"}:
        return ""

    if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        text = render_children(node, downloader, base_url).strip()
        if not text:
            return ""
        return f"\n\n{'#' * int(name[1])} {text}\n\n"

    if name == "p":
        text = render_children(node, downloader, base_url).strip()
        return f"{text}\n\n" if text else ""

    if name == "br":
        return "  \n"

    if name in {"strong", "b"}:
        text = render_children(node, downloader, base_url).strip()
        return f"**{text}**" if text else ""

    if name in {"em", "i"}:
        text = render_children(node, downloader, base_url).strip()
        return f"*{text}*" if text else ""

    if name == "code":
        if node.parent and isinstance(node.parent, Tag) and node.parent.name == "pre":
            return node.get_text()
        text = normalize_inline_text(node.get_text(" ", strip=True))
        return f"`{text}`" if text else ""

    if name == "pre":
        code = node.get_text("\n").strip("\n")
        if not code:
            return ""
        language = normalize_inline_text(node.get("data-lang", "")) or "text"
        return f"\n\n```{language}\n{code}\n```\n\n"

    if name == "a":
        href = html.unescape((node.get("href") or "").strip())
        label = render_children(node, downloader, base_url).strip() or href
        if not href or href.lower().startswith(INVALID_LINK_PREFIXES):
            return label
        if href.startswith("//"):
            href = f"https:{href}"
        elif not href.startswith(("http://", "https://")):
            href = urljoin(base_url, href)
        return f"[{label}]({href})"

    if name == "img":
        source = node.get("src") or node.get("data-src") or node.get("data-original") or ""
        if source.startswith("//"):
            source = f"https:{source}"
        elif source and not source.startswith(("http://", "https://")):
            source = urljoin(base_url, source)
        local_path = downloader.download(source)
        target = local_path or source
        if not target:
            return ""
        alt_text = normalize_inline_text(node.get("alt", "") or "image")
        return f"\n\n![{alt_text}]({target})\n\n"

    if name == "blockquote":
        content = render_children(node, downloader, base_url).strip()
        if not content:
            return ""
        lines = ["> " + line if line else ">" for line in content.splitlines()]
        return "\n\n" + "\n".join(lines) + "\n\n"

    if name == "ul":
        items = [
            render_list_item(child, downloader, base_url, list_level, ordered=False, index=0)
            for child in node.find_all("li", recursive=False)
        ]
        return "\n".join(item for item in items if item).strip() + "\n\n"

    if name == "ol":
        items = [
            render_list_item(child, downloader, base_url, list_level, ordered=True, index=index)
            for index, child in enumerate(node.find_all("li", recursive=False), start=1)
        ]
        return "\n".join(item for item in items if item).strip() + "\n\n"

    if name == "table":
        return render_table(node, downloader, base_url)

    if name in {"div", "section", "article", "span"}:
        return render_children(node, downloader, base_url)

    return render_children(node, downloader, base_url)


def render_list_item(
    node: Tag,
    downloader: ImageDownloader,
    base_url: str,
    list_level: int,
    ordered: bool,
    index: int,
) -> str:
    inline_parts: list[str] = []
    nested_parts: list[str] = []
    for child in node.children:
        if isinstance(child, Tag) and child.name in {"ul", "ol"}:
            nested_parts.append(render_node(child, downloader, base_url, list_level + 1).strip("\n"))
        else:
            inline_parts.append(render_node(child, downloader, base_url, list_level))

    inline_text = normalize_inline_text(" ".join(part for part in inline_parts if part))
    prefix = f"{index}. " if ordered else "- "
    line = ("  " * list_level) + prefix + inline_text if inline_text else ("  " * list_level) + prefix.rstrip()

    nested_text = ""
    if nested_parts:
        indented_blocks: list[str] = []
        for block in nested_parts:
            for sub_line in block.splitlines():
                indented_blocks.append(("  " * (list_level + 1)) + sub_line if sub_line else "")
        nested_text = "\n" + "\n".join(indented_blocks)

    return line.rstrip() + nested_text


def render_table(node: Tag, downloader: ImageDownloader, base_url: str) -> str:
    rows: list[list[str]] = []
    for row in node.find_all("tr"):
        cells: list[str] = []
        for cell in row.find_all(["th", "td"], recursive=False):
            text = normalize_inline_text(render_children(cell, downloader, base_url))
            cells.append(text)
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    header = normalized_rows[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * column_count) + " |",
    ]
    for row in normalized_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n\n" + "\n".join(lines) + "\n\n"


def format_markdown(markdown: str) -> str:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)

    result_lines: list[str] = []
    previous_heading = ""
    in_code_block = False

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            result_lines.append(stripped or line)
            continue

        if in_code_block:
            result_lines.append(line)
            continue

        if not stripped:
            if result_lines and result_lines[-1] != "":
                result_lines.append("")
            continue

        if any(pattern.match(normalize_inline_text(stripped)) for pattern in WECHAT_NOISE_PATTERNS):
            continue

        heading_match = re.match(r"^(#{1,6})\s*(.*)$", stripped)
        if heading_match:
            level = heading_match.group(1)
            heading_text = normalize_inline_text(heading_match.group(2))
            if not heading_text or heading_text == previous_heading:
                continue
            previous_heading = heading_text
            result_lines.append(f"{level} {heading_text}")
            continue

        if stripped.startswith(">"):
            quote_text = normalize_inline_text(stripped[1:])
            result_lines.append(f"> {quote_text}" if quote_text else ">")
            continue

        if stripped.startswith(("- ", "* ", "+ ")):
            result_lines.append("- " + normalize_inline_text(stripped[2:]))
            continue

        ordered_match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if ordered_match:
            result_lines.append(f"{ordered_match.group(1)}. {normalize_inline_text(ordered_match.group(2))}")
            continue

        result_lines.append(normalize_inline_text(stripped))

    while result_lines and result_lines[-1] == "":
        result_lines.pop()

    return "\n".join(result_lines).strip() + "\n"


def build_markdown_document(article: ArticleBundle) -> str:
    header = [
        f"# {article.title}",
        "",
        f"- **来源公众号**：{article.account_name or '未知'}",
        f"- **发布时间**：{article.publish_time or '未知'}",
        f"- **优先级**：{article.priority}",
        (
            "- **命中关键词**："
            + ("、".join(article.matched_keywords) if article.matched_keywords else "无")
        ),
        f"- **原文链接**：{article.source_url}",
        "",
        "---",
        "",
        article.markdown_body.strip(),
        "",
    ]
    return "\n".join(header)


def save_article_bundle(
    article: ArticleBundle,
    output_root: Path,
    save_html: bool = False,
    article_dir: Path | None = None,
) -> dict[str, Any]:
    target_dir = article_dir or build_article_output_dir(
        output_root=output_root,
        publish_time=article.publish_time,
        account_name=article.account_name,
        title=article.title,
    )
    markdown_path = target_dir / f"{sanitize_path_segment(article.title)}.md"
    metadata_path = target_dir / "metadata.json"
    html_path = target_dir / "source.html"

    markdown_path.write_text(build_markdown_document(article), encoding="utf-8")

    metadata = {
        "title": article.title,
        "source_account": article.account_name,
        "publish_time": article.publish_time,
        "matched_keywords": article.matched_keywords,
        "priority": article.priority,
        "source_url": article.source_url,
        "local_path": target_dir.as_posix(),
        "markdown_path": markdown_path.as_posix(),
        "summary_lines": article.summary_lines,
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    written_html_path: str | None = None
    if save_html and article.cleaned_html:
        html_path.write_text(article.cleaned_html, encoding="utf-8")
        written_html_path = html_path.as_posix()

    return {
        "title": article.title,
        "source_account": article.account_name,
        "publish_time": article.publish_time,
        "priority": article.priority,
        "matched_keywords": article.matched_keywords,
        "local_path": target_dir.as_posix(),
        "markdown_path": markdown_path.as_posix(),
        "metadata_path": metadata_path.as_posix(),
        "html_path": written_html_path,
        "summary_lines": article.summary_lines,
        "source_url": article.source_url,
    }


def build_monitor_report(articles: Sequence[dict[str, Any]]) -> dict[str, Any]:
    report = {
        "generated_at": datetime.now(tz=SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "article_count": len(articles),
        "articles": list(articles),
        "urgent_alerts": [],
        "daily_summary": [],
        "weekly_candidates": [],
        "archive_trail": [],
    }

    for article in articles:
        priority = article.get("priority", "P3")
        if priority == "P0":
            report["urgent_alerts"].append(article)
        elif priority == "P1":
            report["daily_summary"].append(article)
        elif priority == "P2":
            report["weekly_candidates"].append(article)
        else:
            report["archive_trail"].append(article)

    return report


def write_monitor_report(output_root: Path, report: dict[str, Any], report_path: Path | None = None) -> Path:
    target = report_path
    if target is None:
        reports_dir = output_root / REPORTS_DIRNAME
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=SHANGHAI_TZ).strftime("%Y%m%d-%H%M%S")
        target = reports_dir / f"{timestamp}_monitor-report.json"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def build_kb_refresh_commands() -> list[list[str]]:
    return [
        [sys.executable, "scripts/update_kb_manifest.py"],
        ["qmd", "collection", "remove", "source_md"],
        ["qmd", "collection", "add", "docs/医院材料学习", "--name", "source_md", "--mask", "**/*.md"],
    ]


def run_kb_refresh(workspace_dir: Path) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    success = True

    for command in build_kb_refresh_commands():
        try:
            result = subprocess.run(
                command,
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            steps.append(
                {
                    "command": command,
                    "returncode": 1,
                    "stdout": "",
                    "stderr": str(error),
                }
            )
            success = False
            break

        step = {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
        steps.append(step)

        is_best_effort_remove = command[:4] == ["qmd", "collection", "remove", "source_md"]
        if result.returncode != 0 and not is_best_effort_remove:
            success = False
            break

    return {"success": success, "steps": steps}


def fetch_article_html(url: str, timeout: int) -> str:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    if response.encoding in (None, "ISO-8859-1"):
        response.encoding = "utf-8"
    return response.text


def process_article_url(
    url: str,
    output_root: Path,
    timeout: int = 30,
    save_html: bool = False,
) -> dict[str, Any]:
    normalized_url = normalize_wechat_url(url)
    if not validate_wechat_url(normalized_url):
        raise ValueError("Invalid WeChat article URL. Only mp.weixin.qq.com and weixin.qq.com are supported.")

    source_html = fetch_article_html(normalized_url, timeout=timeout)
    parts = extract_article_parts(source_html, normalized_url)
    classification = classify_article(
        title=parts["title"],
        body_text=parts["body_text"],
        account_name=parts["account_name"],
    )

    article_dir = build_article_output_dir(
        output_root=output_root,
        publish_time=parts["publish_time"],
        account_name=parts["account_name"],
        title=parts["title"],
    )
    downloader = ImageDownloader(article_dir, timeout=timeout)
    raw_markdown = render_children(parts["content_root"], downloader, normalized_url)
    formatted_markdown = format_markdown(raw_markdown)

    article = ArticleBundle(
        title=parts["title"],
        account_name=parts["account_name"],
        publish_time=parts["publish_time"],
        source_url=normalized_url,
        markdown_body=formatted_markdown,
        cleaned_html=parts["cleaned_html"],
        priority=classification["priority"],
        matched_keywords=classification["matched_keywords"],
        summary_lines=extract_summary_lines(formatted_markdown),
    )

    saved = save_article_bundle(article, output_root, save_html=save_html, article_dir=article_dir)
    saved["image_count"] = downloader.count
    saved["matched_rule"] = classification["matched_rule"]
    return saved


def process_article_urls(
    urls: Sequence[str],
    output_root: Path,
    timeout: int = 30,
    save_html: bool = False,
) -> dict[str, Any]:
    articles: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for url in urls:
        try:
            articles.append(
                process_article_url(
                    url=url,
                    output_root=output_root,
                    timeout=timeout,
                    save_html=save_html,
                )
            )
        except (requests.RequestException, ValueError, OSError) as error:
            failures.append({"url": url, "error": str(error)})

    return {"articles": articles, "failures": failures}


def detect_workspace_dir(explicit_workspace: str | None) -> Path:
    if explicit_workspace:
        return Path(explicit_workspace).resolve()
    return Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch WeChat public articles into the repo monitor layout.",
    )
    parser.add_argument("urls", nargs="+", help="One or more mp.weixin.qq.com article URLs")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output root. Defaults to docs/医院材料学习/公众号每日监测 under the workspace.",
    )
    parser.add_argument(
        "--workspace-dir",
        default=None,
        help="Workspace root. Defaults to the repository root that contains this script.",
    )
    parser.add_argument(
        "--save-html",
        action="store_true",
        help="Save cleaned article HTML alongside the Markdown bundle.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30).",
    )
    parser.add_argument(
        "--refresh-kb",
        action="store_true",
        help="Run the minimum KB refresh flow after saving article Markdown files.",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help="Optional explicit JSON path for the structured monitor report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workspace_dir = detect_workspace_dir(args.workspace_dir)
    output_root = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else (workspace_dir / DEFAULT_OUTPUT_DIR).resolve()
    )

    batch_result = process_article_urls(
        urls=args.urls,
        output_root=output_root,
        timeout=args.timeout,
        save_html=args.save_html,
    )
    saved_articles = batch_result["articles"]
    failures = batch_result["failures"]

    if not saved_articles:
        for failure in failures:
            print(f"处理失败: {failure['url']} -> {failure['error']}", file=sys.stderr)
        sys.exit(1)

    report = build_monitor_report(saved_articles)
    if failures:
        report["failures"] = failures
    report_path = write_monitor_report(
        output_root,
        report,
        Path(args.report_path).resolve() if args.report_path else None,
    )

    kb_refresh = None
    if args.refresh_kb:
        kb_refresh = run_kb_refresh(workspace_dir)
        report["kb_refresh"] = kb_refresh
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("WeChat monitor run complete\n")
    print(f"Articles: {len(saved_articles)}")
    print(f"Urgent alerts (P0): {len(report['urgent_alerts'])}")
    print(f"Daily summary (P1): {len(report['daily_summary'])}")
    print(f"Weekly candidates (P2): {len(report['weekly_candidates'])}")
    print(f"Archive trail (P3/P4): {len(report['archive_trail'])}")
    print(f"Report: {report_path}")
    for article in saved_articles:
        print(
            "- {priority} | {source_account} | {title} | {local_path}".format(
                priority=article["priority"],
                source_account=article["source_account"] or "未知公众号",
                title=article["title"],
                local_path=article["local_path"],
            )
        )

    if failures:
        print(f"Failed URLs: {len(failures)}")
        for failure in failures:
            print(f"- FAILED | {failure['url']} | {failure['error']}")

    if kb_refresh is not None:
        print(f"KB refresh: {'success' if kb_refresh['success'] else 'partial_failure'}")


if __name__ == "__main__":
    main()
