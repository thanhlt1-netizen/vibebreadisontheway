from .base import SourceParser
from .generic import GenericParser
from .sites import (
    TruyenFullParser,
    MetricTruyenParser,
    NovelFullParser,
    RoyalRoadParser,
)

# Domain-specific trước; GenericParser là fallback cuối.
PARSERS: list[type[SourceParser]] = [
    TruyenFullParser,
    MetricTruyenParser,
    NovelFullParser,
    RoyalRoadParser,
]


def pick(url: str) -> SourceParser:
    for cls in PARSERS:
        if cls.match(url):
            return cls()
    return GenericParser()
