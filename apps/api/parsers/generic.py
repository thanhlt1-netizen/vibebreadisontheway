"""
GenericParser — heuristic mạnh để đọc đa số trang truyện / tiểu thuyết / văn bản.
Không phụ thuộc domain cụ thể; domain-specific parser (nếu có) vẫn được ưu tiên trong registry.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from lxml import html as lh
from .base import SourceParser, Chapter, Novel, ChapterRef

# ---------- Noise & navigation patterns ----------
NOISE = re.compile(
    r"(quảng\s*cáo|đọc\s*truyện\s*(tại|online)|donate|facebook|twitter|telegram|"
    r"nguồn\s*:|translator|editor|ads?\b|copyright|bản\s*quyền|"
    r"please\s*enable\s*javascript|turn\s*off\s*ad\s*block|"
    r"subscribe|đăng\s*ký|theo\s*dõi|share\s*this|chia\s*sẻ|"
    r"related\s*(stories|chapters)|truyện\s*cùng\s*tác\s*giả)",
    re.I,
)

NEXT_RE = re.compile(
    r"(chương\s*sau|chap\s*sau|chapter\s*next|next\s*(chapter|chap|page)?|"
    r"tiếp\s*(theo)?|›|»|→|next\b|sau\b)",
    re.I,
)
PREV_RE = re.compile(
    r"(chương\s*trước|chap\s*trước|chapter\s*prev|prev(ious)?\s*(chapter|chap|page)?|"
    r"trước|‹|«|←|prev\b)",
    re.I,
)

# Tiêu đề chương / link danh sách
CHAPTER_TITLE_RE = re.compile(
    r"^(?:"
    r"chương|chuong|chapter|chap|tập|tap|episode|ep|part|phần|phan|"
    r"quyển|quyen|volume|vol|arc|"
    r"第\s*\d+\s*[章节回話话]|"          # 第1章 / 第12話
    r"第\s*[一二三四五六七八九十百千零〇两兩]+\s*[章节回話话]"
    r")"
    r"[\s\-_:：.]*\d*",
    re.I,
)

CHAPTER_URL_RE = re.compile(
    r"(?:chuong|chapter|chap|c|ep|episode|part|tập|tap)[-_/\.]?\d+",
    re.I,
)

# CSS/id hay gặp trên site truyện
CONTENT_SELECTORS = [
    # id
    "//*[@id='chapter-content']",
    "//*[@id='chapter_content']",
    "//*[@id='chapterContent']",
    "//*[@id='content']",
    "//*[@id='novel-content']",
    "//*[@id='novel_content']",
    "//*[@id='book-content']",
    "//*[@id='booktext']",
    "//*[@id='content-text']",
    "//*[@id='reading-content']",
    "//*[@id='chr-content']",
    "//*[@id='chapterText']",
    "//*[@id='story-content']",
    "//*[@id='main-content']",
    # class (contains)
    "//*[contains(@class,'chapter-content')]",
    "//*[contains(@class,'chapter_content')]",
    "//*[contains(@class,'chapterContent')]",
    "//*[contains(@class,'novel-content')]",
    "//*[contains(@class,'novel_content')]",
    "//*[contains(@class,'book-content')]",
    "//*[contains(@class,'reading-content')]",
    "//*[contains(@class,'content-text')]",
    "//*[contains(@class,'chr-content')]",
    "//*[contains(@class,'story-content')]",
    "//*[contains(@class,'entry-content')]",
    "//*[contains(@class,'post-content')]",
    "//*[contains(@class,'article-content')]",
    "//*[contains(@class,'text-left')]",
    "//*[contains(@class,'box-chap')]",
    "//*[contains(@class,'chapter-c')]",
    "//article",
    "//*[contains(@class,'content') and (self::div or self::section)]",
]

# Thẻ / class thường là rác
NOISE_XPATH = (
    "//script|//style|//nav|//header|//footer|//aside|//iframe|//form|"
    "//noscript|//svg|//button|"
    "//*[contains(@class,'ad') or contains(@class,'ads') or contains(@class,'advert') or "
    "contains(@class,'banner') or contains(@class,'popup') or contains(@class,'modal') or "
    "contains(@class,'share') or contains(@class,'social') or contains(@class,'comment') or "
    "contains(@class,'related') or contains(@class,'recommend') or contains(@class,'sidebar') or "
    "contains(@class,'menu') or contains(@class,'nav') or contains(@class,'breadcrumb') or "
    "contains(@id,'ad') or contains(@id,'ads') or contains(@id,'banner')]"
)


def _clean(tree) -> None:
    for bad in tree.xpath(NOISE_XPATH):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)


def _text_len(el) -> int:
    return len(" ".join(t.strip() for t in el.xpath(".//text()") if t and t.strip()))


def _paragraph_score(el) -> float:
    """Điểm readability-ish: ưu tiên khối có nhiều chữ, nhiều <p>, ít link."""
    texts = [t.strip() for t in el.xpath(".//text()") if t and t.strip()]
    full = " ".join(texts)
    n = len(full)
    if n < 80:
        return 0.0
    p_count = len(el.xpath(".//p"))
    br_count = len(el.xpath(".//br"))
    link_text = len(" ".join(a.text_content() or "" for a in el.xpath(".//a")))
    link_ratio = link_text / max(n, 1)
    # phạt nếu gần như toàn link (TOC)
    if link_ratio > 0.45:
        return n * 0.15
    score = n + p_count * 120 + br_count * 25
    score *= max(0.2, 1.0 - link_ratio * 1.5)
    return score


def _best_block(tree):
    """1) Thử selector phổ biến  2) Fallback heuristic trên div/article/section."""
    candidates = []
    for sel in CONTENT_SELECTORS:
        try:
            for el in tree.xpath(sel):
                candidates.append(el)
        except Exception:
            continue

    best, best_score = None, 0.0
    seen = set()
    for el in candidates:
        if id(el) in seen:
            continue
        seen.add(id(el))
        s = _paragraph_score(el)
        if s > best_score:
            best, best_score = el, s

    if best is not None and best_score >= 200:
        return best

    # Fallback: mọi div/article/section
    for el in tree.xpath("//article|//section|//div"):
        s = _paragraph_score(el)
        if s > best_score:
            best, best_score = el, s

    return best if best_score >= 120 else None


def _extract_text(block) -> str:
    """Lấy text có xuống dòng từ <p>, <br>, block elements."""
    for br in block.xpath(".//br"):
        br.tail = "\n" + (br.tail or "")

    # Ưu tiên từng <p>
    paras = []
    p_nodes = block.xpath(".//p")
    if len(p_nodes) >= 2:
        for p in p_nodes:
            t = " ".join(x.strip() for x in p.xpath(".//text()") if x and x.strip())
            t = re.sub(r"\s+", " ", t).strip()
            if t and not NOISE.search(t):
                paras.append(t)
        if paras:
            return "\n".join(paras)

    # Fallback: text_content + split dòng
    raw = block.text_content() or ""
    lines = []
    for line in raw.split("\n"):
        line = re.sub(r"[ \t\u00a0]+", " ", line).strip()
        if not line or NOISE.search(line):
            continue
        # bỏ dòng quá ngắn kiểu nút bấm
        if len(line) < 3:
            continue
        lines.append(line)
    return "\n".join(lines)


def _same_page(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.netloc.lower(), pa.path.rstrip("/")) == (pb.netloc.lower(), pb.path.rstrip("/"))


def _find_nav_link(tree, base: str, pattern: re.Pattern) -> str | None:
    """Find prev/next chapter link; reject same-page / non-http / junk."""
    candidates: list[str] = []

    # 1) rel=next / rel=prev
    rel = "next" if pattern is NEXT_RE else "prev"
    for a in tree.xpath(f"//a[@rel='{rel}' and @href]"):
        href = a.get("href") or ""
        if href and not href.startswith(("#", "javascript:", "mailto:")):
            candidates.append(urljoin(base, href))

    # 2) class / id / text hints
    hints = ("next", "sau", "tiếp") if pattern is NEXT_RE else ("prev", "previous", "truoc", "trước")
    for a in tree.xpath("//a[@href]"):
        blob = " ".join(
            filter(
                None,
                [
                    a.get("class") or "",
                    a.get("id") or "",
                    a.get("aria-label") or "",
                    a.get("title") or "",
                    a.text_content() or "",
                ],
            )
        )
        if pattern.search(blob) or any(h in blob.lower() for h in hints if len(h) > 2):
            href = a.get("href") or ""
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                candidates.append(urljoin(base, href))

    # Prefer chapter-like paths; skip same page / home / list-only
    scored: list[tuple[int, str]] = []
    for full in candidates:
        if _same_page(full, base):
            continue
        path = urlparse(full).path.lower()
        if path in ("", "/"):
            continue
        score = 0
        if CHAPTER_URL_RE.search(path):
            score += 5
        if any(x in path for x in ("chuong", "chapter", "chap", "/c/", "episode")):
            score += 3
        if re.search(r"\d+", path):
            score += 2
        scored.append((score, full))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


def _title_from_tree(tree) -> str:
    for xp in (
        "//h1//text()",
        "//*[contains(@class,'chapter-title')]//text()",
        "//*[contains(@class,'chap-title')]//text()",
        "//*[@id='chapter-title']//text()",
        "//*[@property='og:title']/@content",
        "//title/text()",
    ):
        parts = tree.xpath(xp)
        if parts:
            t = " ".join(p.strip() for p in parts if p and str(p).strip())
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                # bỏ suffix site
                t = re.split(r"\s*[\|\-–—]\s*", t)[0].strip()
                return t or "Chương"
    return "Chương"


def _looks_like_chapter_link(text: str, href: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 120:
        return False
    if CHAPTER_TITLE_RE.search(t):
        return True
    # URL path chứa chapter-ish
    path = urlparse(href).path
    if CHAPTER_URL_RE.search(path):
        return True
    # "1. Title" / "01 - Title" kiểu list
    if re.match(r"^\d{1,4}[\s\.\-_:：]+.+\S", t) and len(t) > 5:
        return True
    return False


def _extract_chapters(tree, base: str) -> list[ChapterRef]:
    seen: set[str] = set()
    chapters: list[ChapterRef] = []

    # Ưu tiên khối list chương
    containers = tree.xpath(
        "//*[contains(@class,'chapter-list') or contains(@class,'chapters') or "
        "contains(@class,'list-chapter') or contains(@class,'chapter_list') or "
        "contains(@id,'chapter-list') or contains(@id,'list-chapter') or "
        "contains(@class,'toc') or contains(@id,'toc')]"
    )
    anchors = []
    for c in containers:
        anchors.extend(c.xpath(".//a[@href]"))
    if not anchors:
        anchors = tree.xpath("//a[@href]")

    for a in anchors:
        href = a.get("href") or ""
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        title = (a.text_content() or "").strip()
        title = re.sub(r"\s+", " ", title)
        full = urljoin(base, href)
        # bỏ query tracking dài
        if full in seen:
            continue
        if not _looks_like_chapter_link(title, full):
            continue
        seen.add(full)
        if not title:
            title = full.rstrip("/").split("/")[-1]
        chapters.append(ChapterRef(title, full))

    return chapters


class GenericParser(SourceParser):
    async def get_chapter(self, url: str, html: str) -> Chapter:
        tree = lh.fromstring(html)
        prev_url = _find_nav_link(tree, url, PREV_RE)
        next_url = _find_nav_link(tree, url, NEXT_RE)
        title = _title_from_tree(tree)

        _clean(tree)
        block = _best_block(tree)
        if block is None:
            raise ValueError(
                "Không tìm thấy nội dung chương. Thử link chương cụ thể (có số chương trong URL) "
                "hoặc trang có văn bản rõ ràng."
            )

        text = _extract_text(block)
        # Lọc dòng nhiễu còn sót
        lines = [ln for ln in text.split("\n") if ln.strip() and not NOISE.search(ln)]
        text = "\n".join(lines).strip()

        if len(text) < 50:
            raise ValueError(
                "Nội dung quá ngắn hoặc trang bị chặn / cần JavaScript. "
                "Thử link khác hoặc bật chế độ trình duyệt (Playwright)."
            )

        return Chapter(title, text, prev_url, next_url)

    async def get_novel(self, url: str, html: str) -> Novel:
        tree = lh.fromstring(html)
        title = _title_from_tree(tree)
        if title == "Chương":
            title = (tree.xpath("//h1//text()") or tree.xpath("//title/text()") or ["Truyện"])[0]
            title = re.sub(r"\s+", " ", str(title)).strip()
            title = re.split(r"\s*[\|\-–—]\s*", title)[0].strip() or "Truyện"

        cover = None
        for xp in (
            "//meta[@property='og:image']/@content",
            "//meta[@name='twitter:image']/@content",
            "//*[contains(@class,'cover')]//img/@src",
            "//img[contains(@class,'cover')]/@src",
        ):
            found = tree.xpath(xp)
            if found:
                cover = urljoin(url, found[0])
                break

        chapters = _extract_chapters(tree, url)
        return Novel(title, cover, chapters)
