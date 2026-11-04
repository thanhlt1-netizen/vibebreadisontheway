"""Split chapter text into TTS-friendly segments."""
from __future__ import annotations

import re
from config import MIN_CHARS


def chunk_text(
    text: str,
    max_len: int = 420,
    min_len: int = MIN_CHARS,
    first_max: int = 85,
) -> list[str]:
    """
    Sentence-aware chunking optimized for local TTS:
    - Short first segment → low time-to-first-audio
    - Body ~420 chars → fewer engine calls
    - Merge micro-fragments so engine never gets tiny strings
    """
    if not text or not text.strip():
        return []

    out: list[str] = []
    sent_re = re.compile(
        r"[^.!?…。！？]+(?:[.!?…。！？]+[\"”')\]]*)?\s*|[.!?…。！？]+",
        re.U,
    )

    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        buf = ""
        parts = sent_re.findall(para) or [para]
        for s in parts:
            s = s.strip()
            if not s:
                continue
            while len(s) > max_len:
                cut = max(
                    s.rfind("，", 0, max_len),
                    s.rfind(",", 0, max_len),
                    s.rfind("、", 0, max_len),
                    s.rfind(" ", 0, max_len),
                    max_len // 2,
                )
                piece = (buf + s[: cut + 1]).strip()
                if piece:
                    out.append(piece)
                buf, s = "", s[cut + 1 :].lstrip()
            if buf and len(buf) + 1 + len(s) > max_len:
                out.append(buf.strip())
                buf = s
            else:
                buf = (buf + " " + s).strip() if buf else s
        if buf.strip():
            out.append(buf.strip())

    merged: list[str] = []
    for c in out:
        if (
            merged
            and (len(merged[-1]) < min_len or len(c) < min_len)
            and len(merged[-1]) + len(c) + 1 <= int(max_len * 1.35)
        ):
            merged[-1] = (merged[-1] + " " + c).strip()
        else:
            merged.append(c)

    if first_max and merged and len(merged[0]) > int(first_max * 1.35):
        head = chunk_text(merged[0], first_max, max(8, min_len // 2), first_max=0)
        merged = head + merged[1:]

    return [c for c in merged if c and len(c.strip()) >= 2]
