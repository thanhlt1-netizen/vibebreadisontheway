"""
GenericParser — “nhìn trang như người đọc”.

Người thật trên web novel:
1. Tìm khối chữ dài ở giữa trang (không phải menu / quảng cáo / list chương).
2. Đọc từ trên xuống dưới trong khối đó.
3. Tìm nút “Chương sau / Chương trước” thường nằm sát trên hoặc dưới khối chữ.
4. Nếu không thấy nút, đôi khi đoán từ số trong URL (…/chuong-12 → …/chuong-13).

Parser này mô phỏng các bước đó thay vì chỉ match CSS máy móc.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse
from lxml import html as lh
from .base import SourceParser, Chapter, Novel, ChapterRef

# ---------- Noise ----------
NOISE = re.compile(
    r"(quảng\s*cáo|đọc\s*truyện\s*(tại|online)|donate|facebook|twitter|telegram|"
    r"nguồn\s*:|translator|editor|ads?\b|copyright|bản\s*quyền|"
    r"please\s*enable\s*javascript|turn\s*off\s*ad\s*block|"
    r"subscribe|đăng\s*ký|theo\s*dõi|share\s*this|chia\s*sẻ|"
    r"related\s*(stories|chapters)|truyện\s*cùng\s*tác\s*giả|"
    r"mục\s*lục|table\s*of\s*contents|danh\s*sách\s*chương)",
    re.I,
)

NEXT_RE = re.compile(
    r"(chương\s*sau|chap(?:ter)?\s*sau|next\s*(?:chapter|chap|page)?|"
    r"tiếp(?:\s*theo)?|›|»|→|\bnext\b)",
    re.I,
)
PREV_RE = re.compile(
    r"(chương\s*trước|chap(?:ter)?\s*trước|prev(?:ious)?\s*(?:chapter|chap|page)?|"
    r"‹|«|←|\bprev\b|trước)",
    re.I,
)

CHAPTER_TITLE_RE = re.compile(
    r"^(?:"
    r"chương|chuong|chapter|chap|tập|tap|episode|ep|part|phần|phan|"
    r"quyển|quyen|volume|vol|arc|"
    r"第\s*\d+\s*[章节回話话]|"
    r"第\s*[一二三四五六七八九十百千零〇两兩]+\s*[章节回話话]"
    r")"
    r"[\s\-_:：.]*\d*",
    re.I,
)

CHAPTER_URL_RE = re.compile(
    r"(?:chuong|chapter|chap|c|ep|episode|part|tập|tap)[-_/\.]?\d+",
    re.I,
)

# Selectors hay gặp — chỉ là gợi ý, vẫn chấm điểm như khối khác
CONTENT_SELECTORS = [
    "//*[@id='chapter-content' or @id='chapter_content' or @id='chapterContent' or @id='chapter-c']",
    "//*[@id='chr-content' or @id='chapterText' or @id='booktext' or @id='content-text']",
    "//*[@id='novel-content' or @id='novel_content' or @id='reading-content' or @id='story-content']",
    "//*[@id='content' or @id='main-content' or @id='book-content']",
    "//*[contains(@class,'chapter-content') or contains(@class,'chapter_content') or contains(@class,'chapter-c')]",
    "//*[contains(@class,'box-chap') or contains(@class,'chr-content') or contains(@class,'reading-content')]",
    "//*[contains(@class,'novel-content') or contains(@class,'entry-content') or contains(@class,'post-content')]",
    "//*[contains(@class,'article-content') or contains(@class,'story-content') or contains(@class,'text-left')]",
    "//article",
    "//*[contains(@class,'content') and (self::div or self::section)]",
]

NOISE_XPATH = (
    "//script|//style|//nav|//header|//footer|//aside|//iframe|//form|"
    "//noscript|//svg|//button|"
    "//*[contains(@class,'ad') or contains(@class,'ads') or contains(@class,'advert') or "
    "contains(@class,'banner') or contains(@class,'popup') or contains(@class,'modal') or "
    "contains(@class,'share') or contains(@class,'social') or contains(@class,'comment') or "
    "contains(@class,'related') or contains(@class,'recommend') or contains(@class,'sidebar') or "
    "contains(@class,'menu') or contains(@class,'nav') or contains(@class,'breadcrumb') or "
    "contains(@class,'pagination') or contains(@class,'pager') or "
    "contains(@id,'ad') or contains(@id,'ads') or contains(@id,'banner') or "
    "contains(@id,'comment') or contains(@id,'footer') or contains(@id,'header')]"
)

# Số chương trong path/query
_CH_NUM = re.compile(
    r"(?:chuong|chapter|chap|episode|ep|part|tập|tap|/c)[-_/\.]?(\d{1,5})",
    re.I,
)
_TRAIL_NUM = re.compile(r"(\d{1,5})(?:\.html?)?/?$", re.I)


def _clean(tree) -> None:
    for bad in tree.xpath(NOISE_XPATH):
        parent = bad.getparent()
        if parent is not None:
            try:
                parent.remove(bad)
            except Exception:
                pass


def _text_len(el) -> int:
    return len(" ".join(t.strip() for t in el.xpath(".//text()") if t and t.strip()))


def _same_page(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.netloc.lower().removeprefix("www."), pa.path.rstrip("/").lower()) == (
        pb.netloc.lower().removeprefix("www."),
        pb.path.rstrip("/").lower(),
    )


def _same_host(a: str, b: str) -> bool:
    return urlparse(a).netloc.lower().removeprefix("www.") == urlparse(b).netloc.lower().removeprefix(
        "www."
    )


def _paragraph_score(el) -> float:
    """
    Giống mắt người: khối “đáng đọc” có nhiều chữ liên tục, nhiều đoạn,
    ít link (không phải mục lục), không nằm trong menu.
    """
    texts = [t.strip() for t in el.xpath(".//text()") if t and t.strip()]
    full = " ".join(texts)
    n = len(full)
    if n < 100:
        return 0.0

    p_count = len(el.xpath(".//p"))
    br_count = len(el.xpath(".//br"))
    links = el.xpath(".//a[@href]")
    link_text = sum(len((a.text_content() or "").strip()) for a in links)
    link_ratio = link_text / max(n, 1)

    # TOC / list chương: rất nhiều link ngắn
    if link_ratio > 0.4 or (len(links) > 12 and n / max(len(links), 1) < 40):
        return n * 0.08

    # Trung bình độ dài “câu/đoạn” — văn xuôi thật dài hơn menu
    chunks = [t for t in texts if len(t) > 20]
    avg = (sum(map(len, chunks)) / len(chunks)) if chunks else 0

    score = n * 1.0 + p_count * 140 + br_count * 20 + avg * 8
    score *= max(0.15, 1.0 - link_ratio * 1.8)

    # Thưởng id/class gợi ý nội dung chương
    blob = f"{el.get('id') or ''} {el.get('class') or ''}".lower()
    if any(
        k in blob
        for k in (
            "chapter",
            "chuong",
            "content",
            "reading",
            "novel",
            "booktext",
            "chr-content",
            "box-chap",
            "entry-content",
            "post-content",
        )
    ):
        score *= 1.35
    if any(k in blob for k in ("sidebar", "menu", "nav", "footer", "header", "comment", "related")):
        score *= 0.25

    tag = (el.tag or "").lower()
    if tag in ("article", "main"):
        score *= 1.15

    return score


def _best_block(tree):
    """1) Selector phổ biến  2) Mọi div/article/section — chọn điểm cao nhất."""
    candidates = []
    for sel in CONTENT_SELECTORS:
        try:
            candidates.extend(tree.xpath(sel))
        except Exception:
            continue
    try:
        candidates.extend(tree.xpath("//article|//main|//div|//section"))
    except Exception:
        pass

    best, best_score = None, 0.0
    seen: set[int] = set()
    for el in candidates:
        i = id(el)
        if i in seen:
            continue
        seen.add(i)
        # Bỏ node quá nông (html/body) — người không đọc cả trang
        tag = (getattr(el, "tag", "") or "").lower()
        if tag in ("html", "body"):
            continue
        s = _paragraph_score(el)
        if s > best_score:
            best, best_score = el, s
    return best


def _extract_text(block) -> str:
    """Lấy chữ theo thứ tự đọc: p / br / dòng — bỏ dòng nhiễu."""
    if block is None:
        return ""
    lines: list[str] = []

    # Ưu tiên <p>
    paras = block.xpath(".//p")
    if paras and sum(_text_len(p) for p in paras) > 80:
        for p in paras:
            t = re.sub(r"[ \t\u00a0]+", " ", (p.text_content() or "")).strip()
            if not t or len(t) < 2 or NOISE.search(t):
                continue
            lines.append(t)
        if lines:
            return "\n".join(lines)

    # Fallback: text_content theo dòng
    raw = block.text_content() or ""
    for line in raw.split("\n"):
        line = re.sub(r"[ \t\u00a0]+", " ", line).strip()
        if not line or len(line) < 3 or NOISE.search(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _link_label(a) -> str:
    return " ".join(
        filter(
            None,
            [
                a.get("class") or "",
                a.get("id") or "",
                a.get("aria-label") or "",
                a.get("title") or "",
                a.get("rel") or "",
                (a.text_content() or "").strip()[:80],
            ],
        )
    )


def _chapter_num(url: str) -> int | None:
    path = urlparse(url).path
    m = _CH_NUM.search(path) or _CH_NUM.search(url)
    if m:
        return int(m.group(1))
    m = _TRAIL_NUM.search(path)
    if m:
        return int(m.group(1))
    return None


def _infer_sibling_url(base: str, delta: int) -> str | None:
    """
    Người đôi khi đoán: chuong-12 → chuong-13.
    Chỉ khi path có số chương rõ.
    """
    u = urlparse(base)
    path = u.path
    num = _chapter_num(base)
    if num is None:
        return None
    new_num = num + delta
    if new_num < 1:
        return None

    def repl_ch(m):
        return m.group(0).replace(m.group(1), str(new_num))

    new_path, nsub = _CH_NUM.subn(repl_ch, path, count=1)
    if nsub == 0:
        new_path, nsub = _TRAIL_NUM.subn(str(new_num) + (m.group(0)[len(m.group(1)) :] if (m := _TRAIL_NUM.search(path)) else ""), path, count=1)
        if nsub == 0:
            return None
    return urlunparse((u.scheme, u.netloc, new_path, u.params, u.query, ""))


def _score_nav_link(href: str, base: str, direction: str, label: str) -> int:
    """Chấm link prev/next như mắt người: cùng site, có số chương, nhãn đúng."""
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return -999
    full = urljoin(base, href)
    if _same_page(full, base):
        return -999
    if not _same_host(full, base):
        return -50

    score = 10
    path = urlparse(full).path.lower()
    lab = label.lower()

    if direction == "next":
        if NEXT_RE.search(lab):
            score += 40
        if any(x in lab for x in ("sau", "next", "tiếp", "›", "»")):
            score += 15
        if PREV_RE.search(lab) and not NEXT_RE.search(lab):
            score -= 30
    else:
        if PREV_RE.search(lab):
            score += 40
        if any(x in lab for x in ("trước", "prev", "‹", "«")):
            score += 15
        if NEXT_RE.search(lab) and not PREV_RE.search(lab):
            score -= 30

    if CHAPTER_URL_RE.search(path) or re.search(r"\d+", path):
        score += 20

    bn, fn = _chapter_num(base), _chapter_num(full)
    if bn is not None and fn is not None:
        if direction == "next" and fn == bn + 1:
            score += 50
        elif direction == "prev" and fn == bn - 1:
            score += 50
        elif direction == "next" and fn > bn:
            score += 15
        elif direction == "prev" and fn < bn:
            score += 15
        elif direction == "next" and fn < bn:
            score -= 25
        elif direction == "prev" and fn > bn:
            score -= 25

    # id/class rõ ràng
    if direction == "next" and any(x in lab for x in ("next_chap", "next-chap", "btn-next", "id_next")):
        score += 35
    if direction == "prev" and any(x in lab for x in ("prev_chap", "prev-chap", "btn-prev", "id_prev")):
        score += 35

    if path in ("", "/"):
        score -= 40
    return score


def _find_nav_link(tree, base: str, pattern: re.Pattern) -> str | None:
    """
    Tìm prev/next như người: quét mọi <a>, chấm điểm, lấy cái hợp lý nhất.
    pattern giữ tương thích sites.py (NEXT_RE / PREV_RE).
    """
    direction = "next" if pattern is NEXT_RE else "prev"
    scored: list[tuple[int, str]] = []

    for a in tree.xpath("//a[@href]"):
        href = a.get("href") or ""
        label = _link_label(a)
        # rel=
        rel = (a.get("rel") or "").lower()
        if direction == "next" and "next" in rel:
            label += " next"
        if direction == "prev" and "prev" in rel:
            label += " prev"

        sc = _score_nav_link(href, base, direction, label)
        if sc < 15:
            continue
        full = urljoin(base, href)
        scored.append((sc, full))

    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


def _nav_near_content(tree, base: str, content_el, direction: str) -> str | None:
    """
    Người hay bấm nút ngay dưới/trên khung chữ.
    Lấy các <a> trong cùng parent / anh em kế bên content.
    """
    if content_el is None:
        return None
    pool = []
    parent = content_el.getparent()
    if parent is not None:
        pool.extend(parent.xpath("./a[@href]|./div//a[@href]|./p//a[@href]"))
        # sibling blocks (pager dưới chapter)
        sib = content_el.getnext()
        steps = 0
        while sib is not None and steps < 4:
            pool.extend(sib.xpath(".//a[@href]|self::a[@href]"))
            sib = sib.getnext()
            steps += 1
        sib = content_el.getprevious()
        steps = 0
        while sib is not None and steps < 3:
            pool.extend(sib.xpath(".//a[@href]|self::a[@href]"))
            sib = sib.getprevious()
            steps += 1

    scored: list[tuple[int, str]] = []
    seen = set()
    for a in pool:
        href = a.get("href") or ""
        full = urljoin(base, href)
        if full in seen:
            continue
        seen.add(full)
        sc = _score_nav_link(href, base, direction, _link_label(a))
        if sc >= 15:
            scored.append((sc + 10, full))  # +10 vì gần content
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


def _resolve_nav(tree, base: str, content_el, direction: str) -> str | None:
    """Thứ tự giống người: gần khung chữ → cả trang → đoán từ số URL."""
    pattern = NEXT_RE if direction == "next" else PREV_RE
    u = _nav_near_content(tree, base, content_el, direction)
    if u:
        return u
    u = _find_nav_link(tree, base, pattern)
    if u:
        return u
    return _infer_sibling_url(base, 1 if direction == "next" else -1)


def _title_from_tree(tree) -> str:
    for xp in (
        "//h1//text()",
        "//*[contains(@class,'chapter-title')]//text()",
        "//*[contains(@class,'chap-title')]//text()",
        "//*[@id='chapter-title']//text()",
        "//a[contains(@class,'chapter-title')]//text()",
        "//*[@property='og:title']/@content",
        "//title/text()",
    ):
        parts = tree.xpath(xp)
        if parts:
            t = " ".join(p.strip() for p in parts if p and str(p).strip())
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                t = re.split(r"\s*[\|\-–—]\s*", t)[0].strip()
                return t or "Chương"
    return "Chương"


def _looks_like_chapter_link(text: str, href: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 120:
        return False
    if CHAPTER_TITLE_RE.search(t):
        return True
    path = urlparse(href).path
    if CHAPTER_URL_RE.search(path):
        return True
    if re.match(r"^\d{1,4}[\s\.\-_:：]+.+\S", t) and len(t) > 5:
        return True
    return False


def _extract_chapters(tree, base: str) -> list[ChapterRef]:
    seen: set[str] = set()
    chapters: list[ChapterRef] = []
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
        title = re.sub(r"\s+", " ", (a.text_content() or "").strip())
        full = urljoin(base, href)
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
        title = _title_from_tree(tree)

        # Làm sạch rác trước khi “nhìn” khối chữ
        _clean(tree)
        block = _best_block(tree)
        if block is None:
            raise ValueError(
                "Không thấy nội dung chương trên trang. "
                "Thử link chương cụ thể (URL có số chương) hoặc trang có văn bản rõ."
            )

        text = _extract_text(block)
        lines = [ln for ln in text.split("\n") if ln.strip() and not NOISE.search(ln)]
        text = "\n".join(lines).strip()

        if len(text) < 50:
            raise ValueError(
                "Nội dung quá ngắn — trang có thể cần JavaScript / bị chặn. "
                "Thử link khác hoặc cài Playwright."
            )

        # Prev/next: gần khung chữ → cả trang → suy từ số URL
        prev_url = _resolve_nav(tree, url, block, "prev")
        next_url = _resolve_nav(tree, url, block, "next")

        # Không cho next/prev trùng nhau hoặc trùng trang hiện tại
        if next_url and _same_page(next_url, url):
            next_url = _infer_sibling_url(url, 1)
        if prev_url and _same_page(prev_url, url):
            prev_url = _infer_sibling_url(url, -1)
        if next_url and prev_url and _same_page(next_url, prev_url):
            # một trong hai sai — tin số chương hơn
            inferred_next = _infer_sibling_url(url, 1)
            inferred_prev = _infer_sibling_url(url, -1)
            if inferred_next:
                next_url = inferred_next
            if inferred_prev:
                prev_url = inferred_prev

        return Chapter(title, text, prev_url, next_url)

    async def get_novel(self, url: str, html: str) -> Novel:
        tree = lh.fromstring(html)
        title = _title_from_tree(tree)
        if title == "Chương":
            title = (tree.xpath("//h1//text()") or ["Truyện"])[0]
            title = re.sub(r"\s+", " ", str(title)).strip()
        cover = None
        for xp in (
            "//meta[@property='og:image']/@content",
            "//img[contains(@class,'cover') or contains(@class,'book')]/@src",
        ):
            found = tree.xpath(xp)
            if found:
                cover = urljoin(url, found[0])
                break
        chapters = _extract_chapters(tree, url)
        if not chapters:
            raise ValueError(
                "Không tìm thấy danh sách chương. Thử trang mục lục hoặc link chương đơn."
            )
        return Novel(title=title or "Truyện", cover=cover, chapters=chapters)
