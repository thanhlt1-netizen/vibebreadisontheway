import re
from config import MIN_CHARS

def chunk_text(text: str, max_len: int = 350, min_len: int = MIN_CHARS, first_max: int = 110) -> list[str]:
    """Tách theo câu thành đoạn <= max_len; gộp đoạn ngắn để mỗi đoạn >= min_len (giới hạn của Cloud API)."""
    out: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para: continue
        buf = ""
        for s in re.findall(r"[^.!?…]+[.!?…]*[\"”')\]]*\s*|[.!?…]+", para) or [para]:
            while len(s) > max_len:                       # câu quá dài: cắt ở dấu phẩy/khoảng trắng
                cut = max(s.rfind(",", 0, max_len), s.rfind(" ", 0, max_len), max_len // 2)
                out.append((buf + s[:cut + 1]).strip()); buf, s = "", s[cut + 1:]
            if len(buf) + len(s) > max_len and buf:
                out.append(buf.strip()); buf = ""
            buf += s
        if buf.strip(): out.append(buf.strip())
    merged: list[str] = []
    for c in out:                                        # gộp đoạn ngắn vào đoạn trước/sau
        if merged and (len(merged[-1]) < min_len or len(c) < min_len) and len(merged[-1]) + len(c) < max_len * 1.5:
            merged[-1] += " " + c
        else:
            merged.append(c)
    if first_max and merged and len(merged[0]) > first_max * 1.5:   # đoạn đầu ngắn → nghe được sớm
        merged[0:1] = chunk_text(merged[0], first_max, min_len, first_max=0)
    return merged
