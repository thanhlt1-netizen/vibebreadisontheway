from .base import SourceParser
from .generic import GenericParser

# Thêm parser riêng cho từng nguồn vào đây (đặt TRƯỚC generic để được ưu tiên).
# Ví dụ:
#   from .truyenfull import TruyenFullParser
#   PARSERS = [TruyenFullParser, ...]
PARSERS: list[type[SourceParser]] = []

def pick(url: str) -> SourceParser:
    for cls in PARSERS:
        if cls.match(url):
            return cls()
    return GenericParser()
