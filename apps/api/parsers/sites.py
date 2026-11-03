"""
Parser theo domain cho các site truyện phổ biến (Việt + một số Anh).
Đặt trước GenericParser trong registry để được ưu tiên.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from lxml import html as lh
from .base import SourceParser, Chapter, Novel, ChapterRef
from .generic import (
    NOISE,
    _clean,
    _extract_text,
    _find_nav_link,
    _title_from_tree,
    NEXT_RE,
    PREV_RE,
)


def _abs(base: str, href: str | None) -> str | None:
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return None
    return urljoin(base, href)


def _paras_from(el) -> str:
    if el is None:
        return ""
    return _extract_text(el)


class TruyenFullParser(SourceParser):
    """truyenfull.* / truyenyy / tương tự layout Việt cổ điển."""
    domains = (
        "truyenfull.vn",
        "truyenfull.vision",
        "truyenfull.com",
        "truyenfull.tv",
        "truyenyy.vn",
        "truyenyy.com",
    )

    async def get_chapter(self, url: str, html: str) -> Chapter:
        tree = lh.fromstring(html)
        title = (
            (tree.xpath("//a[@class='chapter-title' or contains(@class,'chapter-title')]/text()")
             or tree.xpath("//h2/a/text()")
             or tree.xpath("//h1//text()")
             or ["Chương"])[0]
        )
        title = re.sub(r"\s+", " ", str(title)).strip()
        block = None
        for sel in (
            "//div[@id='chapter-c']",
            "//div[contains(@class,'chapter-c')]",
            "//div[@class='chapter-content']",
            "//div[@id='chapter-content']",
        ):
            found = tree.xpath(sel)
            if found:
                block = found[0]
                break
        if block is None:
            from .generic import GenericParser
            return await GenericParser().get_chapter(url, html)
        _clean(tree)
        text = _paras_from(block)
        if len(text) < 40:
            from .generic import GenericParser
            return await GenericParser().get_chapter(url, html)
        prev_url = _find_nav_link(tree, url, PREV_RE)
        next_url = _find_nav_link(tree, url, NEXT_RE)
        # Truyenfull thường có #next_chap / #prev_chap
        if not next_url:
            for a in tree.xpath("//a[@id='next_chap' or contains(@class,'next')]"):
                u = _abs(url, a.get("href"))
                if u:
                    next_url = u
                    break
        if not prev_url:
            for a in tree.xpath("//a[@id='prev_chap' or contains(@class,'prev')]"):
                u = _abs(url, a.get("href"))
                if u:
                    prev_url = u
                    break
        return Chapter(title, text, prev_url, next_url)

    async def get_novel(self, url: str, html: str) -> Novel:
        tree = lh.fromstring(html)
        title = (tree.xpath("//h3[@class='title' or contains(@class,'title')]/text()")
                 or tree.xpath("//h1//text()")
                 or ["Truyện"])[0]
        title = re.sub(r"\s+", " ", str(title)).strip()
        cover = None
        for xp in (
            "//meta[@property='og:image']/@content",
            "//div[contains(@class,'book') or contains(@class,'info')]//img/@src",
        ):
            f = tree.xpath(xp)
            if f:
                cover = urljoin(url, f[0])
                break
        seen, chapters = set(), []
        for a in tree.xpath("//div[contains(@class,'list-chapter')]//a[@href] | //ul[contains(@class,'list-chapter')]//a[@href]"):
            t = (a.text_content() or "").strip()
            u = _abs(url, a.get("href"))
            if not u or u in seen:
                continue
            seen.add(u)
            chapters.append(ChapterRef(t or u, u))
        if not chapters:
            from .generic import GenericParser
            return await GenericParser().get_novel(url, html)
        return Novel(title, cover, chapters)


class MetricTruyenParser(SourceParser):
    """metruyencv / metruyenchu-style."""
    domains = (
        "metruyencv.com",
        "metruyenchu.com",
        "metruyencu.com",
    )

    async def get_chapter(self, url: str, html: str) -> Chapter:
        tree = lh.fromstring(html)
        title = _title_from_tree(tree)
        block = None
        for sel in (
            "//div[contains(@class,'nh-read__content')]",
            "//div[contains(@class,'chapter-content')]",
            "//article",
            "//div[@id='chapter-content']",
        ):
            found = tree.xpath(sel)
            if found:
                block = found[0]
                break
        if block is None:
            from .generic import GenericParser
            return await GenericParser().get_chapter(url, html)
        _clean(tree)
        text = _paras_from(block)
        return Chapter(title, text, _find_nav_link(tree, url, PREV_RE), _find_nav_link(tree, url, NEXT_RE))

    async def get_novel(self, url: str, html: str) -> Novel:
        from .generic import GenericParser
        return await GenericParser().get_novel(url, html)


class NovelFullParser(SourceParser):
    """novelfull / readnovelfull / similar English aggregator."""
    domains = (
        "novelfull.com",
        "novelfull.net",
        "readnovelfull.com",
        "allnovelfull.com",
        "novel-full.com",
    )

    async def get_chapter(self, url: str, html: str) -> Chapter:
        tree = lh.fromstring(html)
        title = _title_from_tree(tree)
        block = None
        for sel in (
            "//div[@id='chapter-content']",
            "//div[contains(@class,'chapter-content')]",
            "//div[@id='chr-content']",
            "//div[contains(@class,'chr-c')]",
        ):
            found = tree.xpath(sel)
            if found:
                block = found[0]
                break
        if block is None:
            from .generic import GenericParser
            return await GenericParser().get_chapter(url, html)
        _clean(tree)
        text = _paras_from(block)
        return Chapter(title, text, _find_nav_link(tree, url, PREV_RE), _find_nav_link(tree, url, NEXT_RE))

    async def get_novel(self, url: str, html: str) -> Novel:
        tree = lh.fromstring(html)
        title = (tree.xpath("//h3[@class='title']/text()") or tree.xpath("//h1//text()") or ["Novel"])[0]
        title = re.sub(r"\s+", " ", str(title)).strip()
        cover = (tree.xpath("//meta[@property='og:image']/@content") or [None])[0]
        if cover:
            cover = urljoin(url, cover)
        seen, chapters = set(), []
        for a in tree.xpath("//ul[contains(@class,'list-chapter')]//a[@href] | //div[contains(@class,'list-chapter')]//a[@href]"):
            t = (a.text_content() or "").strip()
            u = _abs(url, a.get("href"))
            if not u or u in seen:
                continue
            seen.add(u)
            chapters.append(ChapterRef(t or u, u))
        if not chapters:
            from .generic import GenericParser
            return await GenericParser().get_novel(url, html)
        return Novel(title, cover, chapters)


class RoyalRoadParser(SourceParser):
    domains = ("royalroad.com",)

    async def get_chapter(self, url: str, html: str) -> Chapter:
        tree = lh.fromstring(html)
        title = (tree.xpath("//h1[@class='font-white']//text()")
                 or tree.xpath("//h1//text()")
                 or ["Chapter"])[0]
        title = re.sub(r"\s+", " ", str(title)).strip()
        block = None
        for sel in (
            "//div[contains(@class,'chapter-content')]",
            "//div[@class='portlet-body']",
        ):
            found = tree.xpath(sel)
            if found:
                block = found[0]
                break
        if block is None:
            from .generic import GenericParser
            return await GenericParser().get_chapter(url, html)
        _clean(tree)
        text = _paras_from(block)
        return Chapter(title, text, _find_nav_link(tree, url, PREV_RE), _find_nav_link(tree, url, NEXT_RE))

    async def get_novel(self, url: str, html: str) -> Novel:
        from .generic import GenericParser
        return await GenericParser().get_novel(url, html)
