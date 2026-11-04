"""Text cleaning, language detection, translation block split."""
from __future__ import annotations

import html
import re
import unicodedata

# VieNeu v3/v4 only keeps these emotion tags
CUES = ("[cười]", "[thở dài]", "[hắng giọng]")
_BRACKET = re.compile(r"\[([^\[\]\n]{1,200})\]")
_VI = re.compile(
    r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]",
    re.I,
)

# Novel-site noise lines / inline junk
_NOISE_LINE = re.compile(
    r"^\s*(?:"
    r"quảng\s*cáo|đọc\s*truyện\s*(?:tại|online)|please\s*enable|"
    r"chapter\s*source|translator\s*:|editor\s*:|source\s*:|"
    r"https?://\S+|www\.\S+|"
    r"«?\s*(?:prev|next|mục\s*lục|table\s*of\s*contents)\s*»?|"
    r"page\s*\d+\s*(?:of|/)\s*\d+"
    r")\s*$",
    re.I,
)
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_MULTI_PUNCT = re.compile(r"([.!?…]){3,}")
_SPACE = re.compile(r"[ \t\u00a0\u200b\ufeff]{2,}")


def sanitize(text: str) -> str:
    """Clean novel text for display + TTS; keep 3 valid emotion cues."""
    if not text:
        return ""
    t = html.unescape(text)
    t = unicodedata.normalize("NFC", t)

    def f(m):
        raw = m.group(0)
        return raw if raw.lower() in CUES else m.group(1)

    t = _BRACKET.sub(f, t)
    t = _URL.sub("", t)
    lines = []
    for line in t.split("\n"):
        line = line.strip()
        if not line or _NOISE_LINE.match(line):
            continue
        # drop pure separator lines
        if re.fullmatch(r"[\W_]{3,}", line):
            continue
        lines.append(line)
    t = "\n".join(lines)
    t = _MULTI_PUNCT.sub(r"\1\1\1", t)
    t = _SPACE.sub(" ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def for_tts(text: str) -> str:
    """Extra normalize for speech engine (keep meaning, reduce glitches)."""
    t = sanitize(text)
    # Normalize quotes / dashes that confuse some phonemizers
    t = t.replace("…", "...").replace("–", "-").replace("—", " - ")
    t = t.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,.;:!?]){2,}", r"\1", t)
    return t.strip() or "."


def detect_lang(text: str) -> str:
    s = text[:4000]
    n = max(len(re.findall(r"\S", s)), 1)
    hangul = len(re.findall(r"[\uac00-\ud7af]", s))
    kana = len(re.findall(r"[\u3040-\u30ff]", s))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    vi = len(_VI.findall(s))
    latin = len(re.findall(r"[A-Za-z]", s))
    if hangul / n > 0.12:
        return "ko"
    if kana / n > 0.04:
        return "ja"
    if cjk / n > 0.18:
        return "zh"
    if vi / n > 0.035:
        return "vi"
    if latin / n > 0.25:
        return "en"
    return "vi" if vi > 0 else "en"


def split_for_translation(text: str, max_chars: int = 2800) -> list[str]:
    """Group paragraphs into blocks ≤ max_chars without splitting mid-paragraph."""
    blocks, buf = [], ""
    for line in text.split("\n"):
        if buf and len(buf) + len(line) + 1 > max_chars:
            blocks.append(buf)
            buf = ""
        buf += ("\n" if buf else "") + line
    if buf:
        blocks.append(buf)
    return blocks or [text]
