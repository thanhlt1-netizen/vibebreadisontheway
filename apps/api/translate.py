import asyncio, hashlib, json, os
import httpx
from fastapi import HTTPException
import config
from textutil import split_for_translation

LANG = {"zh": "tiếng Trung", "ja": "tiếng Nhật", "ko": "tiếng Hàn", "en": "tiếng Anh", "vi": "tiếng Việt"}
SYSTEM = """Bạn là dịch giả truyện chữ chuyên nghiệp. Dịch từ {src} sang tiếng Việt tự nhiên, đúng văn phong truyện.
Quy tắc:
- Dịch sát nghĩa, giữ giọng kể, xưng hô và sắc thái cảm xúc của nhân vật; không tóm tắt, không bỏ sót câu.
- Mỗi dòng nguồn là một đoạn; trả về đúng số dòng đó, giữ nguyên thứ tự.
- Chỉ trả về bản dịch, không giải thích, không ghi chú.
- Tên riêng và thuật ngữ theo bảng sau (nếu có), nhất quán trong toàn bài:
{glossary}
- Có thể chèn [cười], [thở dài], [hắng giọng] khi văn bản rõ ràng mô tả hành động đó; tuyệt đối không dùng thẻ khác."""

def _path(k): return os.path.join(config.DATA_DIR, "translations", k + ".json")

async def _call(client, key, system, user):
    r = await client.post("https://api.anthropic.com/v1/messages", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": config.TRANSLATE_MODEL, "max_tokens": 8000, "system": system,
              "messages": [{"role": "user", "content": user}]})
    if r.status_code == 401: raise HTTPException(401, "API key Anthropic không hợp lệ")
    if r.status_code == 429: raise HTTPException(429, "Anthropic đang giới hạn tốc độ, thử lại sau")
    if r.status_code != 200: raise HTTPException(502, f"Dịch lỗi ({r.status_code})")
    return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text").strip()

async def translate(text: str, src: str, glossary: dict[str, str], key: str | None) -> str:
    key = key or config.ANTHROPIC_KEY
    if not key: raise HTTPException(400, "Thiếu API key Anthropic (header X-Anthropic-Key hoặc ANTHROPIC_API_KEY)")
    ck = hashlib.sha256(json.dumps([text, src, glossary, config.TRANSLATE_MODEL], ensure_ascii=False).encode()).hexdigest()
    if os.path.exists(_path(ck)): return json.load(open(_path(ck), encoding="utf-8"))["t"]
    gl = "\n".join(f"{a} = {b}" for a, b in glossary.items()) or "(không có)"
    system = SYSTEM.format(src=LANG.get(src, src), glossary=gl)
    blocks = split_for_translation(text)
    sem = asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=180) as c:
        async def one(i, b):
            ctx = f"[Ngữ cảnh đoạn trước, chỉ để tham khảo, KHÔNG dịch lại]\n{blocks[i-1][-300:]}\n\n" if i else ""
            async with sem:
                return await _call(c, key, system, f"{ctx}[Văn bản cần dịch]\n{b}")
        out = "\n".join(await asyncio.gather(*(one(i, b) for i, b in enumerate(blocks))))
    os.makedirs(os.path.dirname(_path("x")), exist_ok=True)
    json.dump({"t": out}, open(_path(ck), "w", encoding="utf-8"), ensure_ascii=False)
    return out
