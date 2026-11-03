import asyncio, dataclasses, re
from urllib.parse import urlparse
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import os
from pydantic import BaseModel, Field
import config
from chunker import chunk_text
from fetcher import fetch
from parsers.registry import pick
from service import JOBS, load_chapter, start_prefetch
from textutil import CUES, detect_lang, sanitize
from translate import translate
from tts.providers import provider

app = FastAPI(title="VibeRead API", version="0.3")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Cache", "X-Sample-Rate"])

@app.on_event("startup")
async def _warm():
    if config.TTS_PROVIDER == "sdk":
        asyncio.create_task(provider.warmup())     # nạp model nền, không chặn việc mở app

@app.get("/api/health")
async def health():
    sdk = config.TTS_PROVIDER == "sdk"
    st = provider.status() if sdk and hasattr(provider, "status") else {}
    return {
        "ok": True,
        "tts_ready": provider.ready if sdk else True,
        "tts_error": getattr(provider, "err", None),
        "tts_downloading": st.get("downloading", False),
        "tts_download_msg": st.get("download_msg", ""),
        "tts_cached": st.get("bundled_or_cached", False),
        "ms_per_char": getattr(provider, "ms_per_char", None),
        "data_dir": config.DATA_DIR,
        "tts": config.TTS_PROVIDER,
        "tts_key": bool(config.API_KEY) or config.TTS_PROVIDER != "cloud",
        "translate_key": bool(config.ANTHROPIC_KEY or config.OPENAI_KEY or config.DEEPSEEK_KEY),
        "playwright": __import__("fetcher", fromlist=["playwright_available"]).playwright_available(),
    }

@app.post("/api/tts/download-model")
async def download_model():
    """Tai / cai model VieNeu thu cong khi ban cai khong bundle model."""
    if config.TTS_PROVIDER != "sdk":
        return {"ok": True, "message": "Chi can thiet o che do sdk"}
    if not hasattr(provider, "download_model"):
        raise HTTPException(400, "Provider khong ho tro tai model")
    if getattr(provider, "downloading", False):
        return {"ok": False, "message": "Dang tai model, vui long cho"}
    ok, msg = await provider.download_model()
    if not ok:
        raise HTTPException(500, msg)
    return {"ok": True, "message": msg}

@app.get("/api/tts/status")
async def tts_status():
    if config.TTS_PROVIDER != "sdk" or not hasattr(provider, "status"):
        return {"ready": True, "provider": config.TTS_PROVIDER}
    return provider.status()

@app.get("/api/resolve")
async def resolve(url: str):
    path = urlparse(url).path.lower()
    # Nhận diện URL chương: chuong/chapter/chap/ep/episode/part + số, hoặc /c12, /chapter-12.html
    kind = "chapter" if re.search(
        r"(chuong|chapter|chap|episode|ep|part|tập|tap|/c)[-_/\.]?\d+",
        path,
        re.I,
    ) else "novel"
    return {"kind": kind, "parser": type(pick(url)).__name__}

@app.get("/api/novel")
async def novel(url: str):
    return dataclasses.asdict(await pick(url).get_novel(url, await fetch(url)))

@app.get("/api/chapter")
async def chapter(url: str):
    return await load_chapter(url)

# ---------- Dịch ----------
class TranslateReq(BaseModel):
    url: str | None = None
    text: str | None = None
    title: str | None = None
    source_lang: str | None = None            # bỏ trống = tự nhận diện
    glossary: dict[str, str] = Field(default_factory=dict)
    novel_key: str | None = None              # khóa glossary theo truyện (url novel)

@app.post("/api/translate")
async def translate_ep(
    req: TranslateReq,
    x_anthropic_key: str | None = Header(None),
    x_openai_key: str | None = Header(None),
    x_api_key: str | None = Header(None),
):
    if req.url:
        ch = await load_chapter(req.url)
        text, title = ch["text"], ch["title"]
    elif req.text:
        text, title = sanitize(req.text), req.title or ""
    else:
        raise HTTPException(400, "Cần url hoặc text")
    src = req.source_lang or detect_lang(text)
    if src == "vi":
        return {"source_lang": "vi", "title": title, "text": text, "chunks": chunk_text(text), "translated": False}
    # Ưu tiên header key người dùng nhập (Anthropic hoặc DeepSeek/OpenAI)
    user_key = x_anthropic_key or x_openai_key or x_api_key
    body = await translate(
        f"{title}\n{text}" if title else text,
        src,
        req.glossary,
        user_key,
        novel_key=req.novel_key,
    )
    new_title, _, rest = body.partition("\n") if title else ("", "", body)
    rest = sanitize(rest if title else body)
    return {
        "source_lang": src,
        "title": new_title or title,
        "text": rest,
        "chunks": chunk_text(rest),
        "translated": True,
        "original_chunks": chunk_text(text),
    }

# ---------- TTS ----------
class TTSReq(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str | None = None

@app.post("/api/tts")
async def tts(req: TTSReq, request: Request):
    text = sanitize(req.text)
    if len(text) < config.MIN_CHARS: text = text.ljust(config.MIN_CHARS)
    async def alive(): return not await request.is_disconnected()
    data, hit = await provider.cached(text, req.voice or config.DEFAULT_VOICE, alive)
    mime = "audio/mpeg" if provider.fmt == "mp3" else "audio/wav"
    return Response(data, media_type=mime, headers={"X-Cache": "hit" if hit else "miss"})

@app.post("/api/tts/stream")
async def tts_stream(req: TTSReq):
    """PCM s16le mono, phát ngay khi sinh. Tần số trong header X-Sample-Rate (không cache)."""
    text = sanitize(req.text)
    if len(text) < config.MIN_CHARS: text = text.ljust(config.MIN_CHARS)
    rate, gen = await provider.stream(text, req.voice or config.DEFAULT_VOICE)
    return StreamingResponse(gen, media_type="audio/L16", headers={"X-Sample-Rate": str(rate)})

@app.get("/api/voices")
async def voices(): return await provider.voices()

@app.get("/api/emotion-tags")
async def emotion_tags():
    local = {"cues": list(CUES), "source": "builtin"}
    if config.TTS_PROVIDER != "cloud": return local
    try: return await provider.get_json("/emotion-tags?engine=v4")
    except HTTPException: return local

@app.get("/api/balance")
async def balance():
    if config.TTS_PROVIDER != "cloud": return {"provider": "local"}
    return await provider.get_json("/balance")

# ---------- Tải trước ----------
class PrefetchReq(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=3)
    voice: str | None = None

@app.post("/api/prefetch")
async def prefetch(req: PrefetchReq):
    return {"job": start_prefetch(req.urls, req.voice or config.DEFAULT_VOICE)}

@app.get("/api/prefetch/{job}")
async def prefetch_status(job: str):
    if job not in JOBS: raise HTTPException(404, "Không có job")
    return JOBS[job]

class EstimateReq(BaseModel):
    text: str

@app.post("/api/estimate")
async def estimate(req: EstimateReq):
    chunks = chunk_text(sanitize(req.text))
    return {"chunks": len(chunks), "chars": sum(map(len, chunks)), "billed": config.TTS_PROVIDER == "cloud",
            "note": "Cloud: token = ký tự × hệ số engine v4 × globalMultiplier (xem /api/balance, /v1/engines)"}

# PWA tĩnh — phải mount SAU các route /api
import sys
_BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
app.mount("/", StaticFiles(directory=os.path.join(_BASE, "static"), html=True), name="static")
