import asyncio, dataclasses, time, uuid
from fastapi import HTTPException
import config
from chunker import chunk_text
from fetcher import fetch
from parsers.registry import pick
from textutil import sanitize, detect_lang
from tts.providers import provider

# In-process chapter cache (parsed + chunked) — big win when reopening / prefetch
_CH_CACHE: dict[str, tuple[float, dict]] = {}
_CH_TTL = 900  # 15 min


async def load_chapter(url: str, *, bypass_cache: bool = False) -> dict:
    from fetcher import normalize_url
    url = normalize_url(url)
    now = time.time()
    if not bypass_cache:
        hit = _CH_CACHE.get(url)
        if hit and now - hit[0] < _CH_TTL:
            return hit[1]
    try:
        c = await pick(url).get_chapter(url, await fetch(url))
    except ValueError as e:
        raise HTTPException(422, str(e))
    d = dataclasses.asdict(c)
    d["text"] = sanitize(c.text)
    d["lang"] = detect_lang(d["text"])
    d["chunks"] = chunk_text(d["text"])
    d["chars"] = len(d["text"])
    if len(_CH_CACHE) > 80:
        _CH_CACHE.pop(next(iter(_CH_CACHE)))
    _CH_CACHE[url] = (now, d)
    return d

JOBS: dict[str, dict] = {}

async def _prefetch(job: str, urls: list[str], voice: str):
    j = JOBS[job]
    try:
        for u in urls:
            ch = await load_chapter(u)
            if ch["lang"] != "vi":
                j["items"].append({"url": u, "status": "skipped", "reason": "cần dịch trước"}); continue
            if ch["chars"] > config.MAX_PREFETCH_CHARS:
                j["items"].append({"url": u, "status": "skipped", "reason": "chương quá dài"}); continue
            j["total"] += len(ch["chunks"])
            for t in ch["chunks"]:
                await provider.cached(t, voice); j["done"] += 1
            j["items"].append({"url": u, "status": "ready", "chunks": len(ch["chunks"])})
        j["status"] = "done"
    except HTTPException as e:
        j["status"], j["error"] = "error", str(e.detail)
    except Exception as e:
        j["status"], j["error"] = "error", e.__class__.__name__

def start_prefetch(urls: list[str], voice: str) -> str:
    job = uuid.uuid4().hex[:12]
    if len(JOBS) > 50: JOBS.pop(next(iter(JOBS)))
    JOBS[job] = {"status": "running", "done": 0, "total": 0, "items": []}
    asyncio.create_task(_prefetch(job, urls, voice))
    return job
