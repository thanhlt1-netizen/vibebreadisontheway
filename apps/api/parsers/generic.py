import re
from urllib.parse import urljoin
from lxml import html as lh
from .base import SourceParser, Chapter, Novel, ChapterRef

NOISE = re.compile(r"(quảng cáo|đọc truyện tại|donate|facebook|nguồn:|translator|ads?\b)", re.I)
NEXT = re.compile(r"(chương sau|chap sau|next|tiếp|›|»)", re.I)
PREV = re.compile(r"(chương trước|chap trước|prev|trước|‹|«)", re.I)

def _clean(tree):
    for bad in tree.xpath("//script|//style|//nav|//header|//footer|//aside|//iframe|//form"):
        bad.getparent().remove(bad)

def _best_block(tree):
    """Chọn khối có nhiều chữ nhất nằm trực tiếp trong <p>/<br> (heuristic kiểu readability)."""
    best, score = None, 0
    for el in tree.xpath("//div|//article|//section"):
        text = " ".join(t.strip() for t in el.xpath("./text()|./p/text()") if t.strip())
        if len(text) > score:
            best, score = el, len(text)
    return best

def _link(tree, base, pattern):
    for a in tree.xpath("//a[@href]"):
        label = (a.text_content() or "") + " " + (a.get("rel") or "") + " " + (a.get("id") or "")
        if pattern.search(label):
            return urljoin(base, a.get("href"))
    return None

class GenericParser(SourceParser):
    async def get_chapter(self, url, html):
        tree = lh.fromstring(html)
        prev_url, next_url = _link(tree, url, PREV), _link(tree, url, NEXT)
        title = (tree.xpath("//h1//text()") or tree.xpath("//title/text()") or ["Chương"])[0].strip()
        _clean(tree)
        block = _best_block(tree)
        if block is None:
            raise ValueError("Không tìm thấy nội dung chương")
        for br in block.xpath(".//br"):
            br.tail = "\n" + (br.tail or "")
        paras = [p.strip() for p in block.text_content().split("\n")]
        text = "\n".join(p for p in paras if p and not NOISE.search(p))
        return Chapter(title, text, prev_url, next_url)

    async def get_novel(self, url, html):
        tree = lh.fromstring(html)
        title = (tree.xpath("//h1//text()") or tree.xpath("//title/text()") or ["Truyện"])[0].strip()
        cover = (tree.xpath("//meta[@property='og:image']/@content") or [None])[0]
        seen, chapters = set(), []
        for a in tree.xpath("//a[@href]"):
            t = (a.text_content() or "").strip()
            if re.match(r"^(chương|chapter|chap|c)\s*\d+", t, re.I):
                u = urljoin(url, a.get("href"))
                if u not in seen:
                    seen.add(u); chapters.append(ChapterRef(t, u))
        return Novel(title, cover, chapters)
