from .base import SourceParser
from .generic import GenericParser

# Thêm parser riêng cho từng nguồn vào đây (đặt trước generic).
PARSERS: list[type[SourceParser]] = []

def pick(url: str) -> SourceParser:
    for cls in PARSERS:
        if cls.match(url):
            return cls()
    return GenericParser()
