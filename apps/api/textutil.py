import re

# v4 chỉ đọc được 3 thẻ này; mọi thẻ khác bị server VieNeu xoá khỏi văn bản.
CUES = ("[cười]", "[thở dài]", "[hắng giọng]")
_BRACKET = re.compile(r"\[([^\[\]\n]{1,200})\]")

def sanitize(text: str) -> str:
    """Giữ 3 thẻ cảm xúc hợp lệ; [Level up!] kiểu hệ thống → bỏ ngoặc để vẫn được đọc."""
    def f(m):
        return m.group(0) if m.group(0).lower() in CUES else m.group(1)
    t = _BRACKET.sub(f, text)
    t = re.sub(r"[ \t\u00a0]{2,}", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()

_VI = re.compile(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.I)

def detect_lang(text: str) -> str:
    s = text[:3000]
    n = max(len(re.findall(r"\S", s)), 1)
    hangul = len(re.findall(r"[\uac00-\ud7af]", s)); kana = len(re.findall(r"[\u3040-\u30ff]", s))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s)); vi = len(_VI.findall(s))
    if hangul / n > .15: return "ko"
    if kana / n > .05: return "ja"
    if cjk / n > .2: return "zh"
    return "vi" if vi / n > .04 else "en"

def split_for_translation(text: str, max_chars: int = 3000) -> list[str]:
    """Gom các đoạn (mỗi dòng một đoạn) thành khối ≤ max_chars, không cắt giữa đoạn."""
    blocks, buf = [], ""
    for line in text.split("\n"):
        if buf and len(buf) + len(line) + 1 > max_chars:
            blocks.append(buf); buf = ""
        buf += ("\n" if buf else "") + line
    if buf: blocks.append(buf)
    return blocks
