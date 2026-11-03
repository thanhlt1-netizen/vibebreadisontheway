"""
Dịch truyện chất lượng cao — tham khảo pipeline kiểu wenyi / literary MT:
- Prompt sát nghĩa, giữ văn phong truyện, xưng hô, cảm xúc
- Dịch tuần tự theo khối + ngữ cảnh đoạn trước (tránh đứt mạch)
- Glossary tự động + người dùng (tên riêng nhất quán)
- Đa nhà cung cấp: Anthropic Claude, OpenAI-compatible (DeepSeek, v.v.)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re

import httpx
from fastapi import HTTPException

import config
from textutil import split_for_translation

LANG = {
    "zh": "tiếng Trung",
    "ja": "tiếng Nhật",
    "ko": "tiếng Hàn",
    "en": "tiếng Anh",
    "vi": "tiếng Việt",
}

# Prompt literary — sát nghĩa, không tóm tắt, giữ nhịp kể (cảm hứng wenyi / DITING)
SYSTEM = """Bạn là dịch giả truyện chữ chuyên nghiệp (web novel / light novel / tiểu thuyết).
Nhiệm vụ: dịch từ {src} sang tiếng Việt tự nhiên, đúng văn phong truyện.

Quy tắc bắt buộc:
1. Dịch SÁT NGHĨA và ĐẦY ĐỦ — không tóm tắt, không bỏ sót câu, không thêm bình luận.
2. Giữ giọng kể, xưng hô (hắn/nàng/ta/ngươi…), sắc thái cảm xúc và nhịp đối thoại.
3. Tên riêng, địa danh, thuật ngữ: dùng bảng glossary bên dưới; nếu chưa có thì phiên âm/Hán-Việt nhất quán trong toàn bài.
4. Mỗi dòng nguồn là một đoạn; trả về ĐÚNG số dòng đó, cùng thứ tự. Không đánh số, không markdown.
5. Chỉ trả về bản dịch thuần — không giải thích, không ghi chú, không bọc trong dấu ngoặc kép.
6. Có thể chèn đúng 3 thẻ cảm xúc khi văn bản mô tả rõ: [cười], [thở dài], [hắng giọng]. Không dùng thẻ khác.

Bảng thuật ngữ (ưu tiên tuyệt đối):
{glossary}
"""

# Tên kiểu CJK / Latin viết hoa — gợi ý glossary thô
_NAME_CJK = re.compile(r"[\u4e00-\u9fff]{2,4}")
_NAME_LATIN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")


def _path(k: str) -> str:
    return os.path.join(config.DATA_DIR, "translations", k + ".json")


def _glossary_path(novel_key: str) -> str:
    return os.path.join(config.DATA_DIR, "glossaries", novel_key + ".json")


def load_glossary(novel_key: str | None) -> dict[str, str]:
    if not novel_key:
        return {}
    p = _glossary_path(novel_key)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_glossary(novel_key: str | None, gl: dict[str, str]) -> None:
    if not novel_key or not gl:
        return
    os.makedirs(os.path.dirname(_glossary_path("x")), exist_ok=True)
    json.dump(gl, open(_glossary_path(novel_key), "w", encoding="utf-8"), ensure_ascii=False, indent=0)


def suggest_terms(text: str, src: str, limit: int = 40) -> list[str]:
    """Gợi ý thuật ngữ từ văn bản nguồn (chưa dịch)."""
    found: list[str] = []
    seen: set[str] = set()
    if src in ("zh", "ja"):
        for m in _NAME_CJK.findall(text[:8000]):
            if m not in seen:
                seen.add(m)
                found.append(m)
    for m in _NAME_LATIN.findall(text[:8000]):
        if m not in seen and len(m) > 2:
            seen.add(m)
            found.append(m)
    return found[:limit]


def _provider_and_key(header_key: str | None) -> tuple[str, str, str]:
    """Returns (provider, api_key, model). provider: anthropic | openai_compat"""
    key = (header_key or "").strip()
    if not key:
        key = (config.ANTHROPIC_KEY or config.OPENAI_KEY or config.DEEPSEEK_KEY or "").strip()
    if not key:
        raise HTTPException(
            400,
            "Thiếu API key dịch. Nhập key Anthropic (sk-ant-…) hoặc DeepSeek/OpenAI trong Cài đặt.",
        )

    forced = (config.TRANSLATE_PROVIDER or "auto").lower()
    if forced == "anthropic" or key.startswith("sk-ant-"):
        return "anthropic", key, config.TRANSLATE_MODEL
    if forced in ("openai", "openai_compat", "deepseek"):
        return "openai_compat", key, config.OPENAI_MODEL
    # auto: sk-ant- → Anthropic; còn lại → OpenAI-compatible (DeepSeek)
    if key.startswith("sk-ant-"):
        return "anthropic", key, config.TRANSLATE_MODEL
    return "openai_compat", key, config.OPENAI_MODEL


async def _call_anthropic(client: httpx.AsyncClient, key: str, model: str, system: str, user: str) -> str:
    r = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 8000,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
    )
    if r.status_code == 401:
        raise HTTPException(401, "API key Anthropic không hợp lệ")
    if r.status_code == 429:
        raise HTTPException(429, "Anthropic đang giới hạn tốc độ, thử lại sau")
    if r.status_code != 200:
        raise HTTPException(502, f"Dịch Anthropic lỗi ({r.status_code})")
    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()


async def _call_openai(client: httpx.AsyncClient, key: str, model: str, system: str, user: str) -> str:
    base = config.OPENAI_BASE_URL.rstrip("/")
    r = await client.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={
            "model": model,
            "temperature": 0.3,
            "max_tokens": 8000,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    )
    if r.status_code == 401:
        raise HTTPException(401, "API key OpenAI/DeepSeek không hợp lệ")
    if r.status_code == 429:
        raise HTTPException(429, "Nhà cung cấp đang giới hạn tốc độ, thử lại sau")
    if r.status_code != 200:
        raise HTTPException(502, f"Dịch lỗi ({r.status_code}): {(r.text or '')[:200]}")
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        raise HTTPException(502, "Phản hồi dịch không hợp lệ")


async def translate(
    text: str,
    src: str,
    glossary: dict[str, str] | None,
    key: str | None,
    novel_key: str | None = None,
) -> str:
    provider, api_key, model = _provider_and_key(key)
    glossary = dict(glossary or {})
    # Merge persisted glossary for this novel
    stored = load_glossary(novel_key)
    for k, v in stored.items():
        glossary.setdefault(k, v)

    ck = hashlib.sha256(
        json.dumps([text, src, glossary, provider, model], ensure_ascii=False).encode()
    ).hexdigest()
    cache_file = _path(ck)
    if os.path.exists(cache_file):
        return json.load(open(cache_file, encoding="utf-8"))["t"]

    gl_txt = "\n".join(f"{a} = {b}" for a, b in glossary.items()) or "(chưa có — hãy dịch tên nhất quán)"
    system = SYSTEM.format(src=LANG.get(src, src), glossary=gl_txt)
    blocks = split_for_translation(text)

    # Sequential with rolling context (wenyi-style continuity) — better consistency than full parallel
    out_parts: list[str] = []
    async with httpx.AsyncClient(timeout=180) as client:
        for i, block in enumerate(blocks):
            ctx = ""
            if i and out_parts:
                # Previous translated tail as context only
                prev = out_parts[-1][-400:]
                ctx = (
                    "[Ngữ cảnh bản dịch đoạn trước — chỉ tham khảo, KHÔNG dịch lại]\n"
                    f"{prev}\n\n"
                )
            user = f"{ctx}[Văn bản cần dịch]\n{block}"
            if provider == "anthropic":
                part = await _call_anthropic(client, api_key, model, system, user)
            else:
                part = await _call_openai(client, api_key, model, system, user)
            out_parts.append(part)
            # Light pause to reduce rate limits on free tiers
            if i + 1 < len(blocks):
                await asyncio.sleep(0.15)

    out = "\n".join(out_parts)
    os.makedirs(os.path.dirname(_path("x")), exist_ok=True)
    json.dump({"t": out}, open(cache_file, "w", encoding="utf-8"), ensure_ascii=False)

    # Persist glossary hints if novel_key set
    if novel_key and glossary:
        save_glossary(novel_key, glossary)
    return out
