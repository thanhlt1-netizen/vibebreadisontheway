from dataclasses import dataclass, field
from urllib.parse import urlparse

@dataclass
class ChapterRef:
    title: str
    url: str

@dataclass
class Chapter:
    title: str
    text: str
    prev_url: str | None = None
    next_url: str | None = None

@dataclass
class Novel:
    title: str
    cover: str | None = None
    chapters: list[ChapterRef] = field(default_factory=list)

class SourceParser:
    """Mỗi nguồn truyện là một lớp con: khai báo domains, override get_novel/get_chapter."""
    domains: tuple[str, ...] = ()

    @classmethod
    def match(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in cls.domains)

    async def get_novel(self, url: str, html: str) -> Novel: raise NotImplementedError
    async def get_chapter(self, url: str, html: str) -> Chapter: raise NotImplementedError
