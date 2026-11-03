import asyncio, hashlib, os, tempfile, threading, time
import httpx
from fastapi import HTTPException
import config

class TTSError(HTTPException): ...

def _map(r: httpx.Response):
    msg = {401: "API key VieNeu không hợp lệ", 403: "Hết token hoặc gói không hỗ trợ",
           400: "Giọng/văn bản bị từ chối (kiểm tra voice id của engine v4)",
           429: "Vượt giới hạn tốc độ/hạn mức", 503: "Chưa có worker TTS, thử lại sau"}.get(r.status_code, "TTS lỗi")
    raise TTSError(502 if r.status_code >= 500 else r.status_code, f"{msg} ({r.text[:160]})")

class Provider:
    name = ""; fmt = "mp3"
    def __init__(self):
        self.base = config.CLOUD_URL if config.TTS_PROVIDER == "cloud" else config.LOCAL_URL
        self.cloud = config.TTS_PROVIDER == "cloud"
        self.headers = {"Authorization": f"Bearer {config.API_KEY}"} if self.cloud else {}
        self.fmt = "mp3" if self.cloud else "wav"   # server local chỉ hỗ trợ pcm/wav
        self.sem = asyncio.Semaphore(4)              # giữ dưới giới hạn 300 req/phút & số kết nối

    def key(self, text: str, voice: str) -> str:
        return hashlib.sha256(f"{config.TTS_PROVIDER}|{voice}|{text}".encode()).hexdigest()

    async def synth(self, text: str, voice: str, alive=None) -> bytes:
        body = {"input": text, "voice": voice, "response_format": self.fmt}
        if self.cloud: body["engine"] = "v4"
        else: body["model"] = config.LOCAL_MODEL
        async with self.sem, httpx.AsyncClient(timeout=120) as c:
            for attempt in range(3):
                r = await c.post(f"{self.base}/audio/speech", json=body, headers=self.headers)
                if r.status_code == 429 and "retry-after" in r.headers and attempt < 2:
                    await asyncio.sleep(min(int(r.headers["retry-after"]), 30)); continue
                if r.status_code != 200: _map(r)
                return r.content
        raise TTSError(429, "Vượt giới hạn tốc độ")

    async def voices(self) -> list[dict]:
        url = f"{self.base}/voices" + ("?engine=v4" if self.cloud else "")
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers=self.headers)
        if r.status_code != 200: _map(r)
        d = r.json()
        return d["voices"] if isinstance(d, dict) and "voices" in d else d

    async def stream(self, text: str, voice: str):
        """PCM s16le streaming. Trả (sample_rate, async-generator bytes)."""
        body = {"input": text, "voice": voice, "response_format": "pcm", "stream_format": "audio"}
        if self.cloud: body.update(engine="v4", sample_rate=24000)
        else: body["model"] = config.LOCAL_MODEL
        rate = 24000 if self.cloud else 48000
        client = httpx.AsyncClient(timeout=None)
        req = client.build_request("POST", f"{self.base}/audio/speech", json=body, headers=self.headers)
        r = await client.send(req, stream=True)
        if r.status_code != 200:
            await r.aread(); await client.aclose(); _map(r)
        async def gen():
            try:
                async for b in r.aiter_bytes(4096): yield b
            finally:
                await r.aclose(); await client.aclose()
        return rate, gen()

    async def get_json(self, path: str):
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self.base}{path}", headers=self.headers)
        if r.status_code != 200: _map(r)
        return r.json()

    async def cached(self, text: str, voice: str, alive=None) -> tuple[bytes, bool]:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        path = os.path.join(config.CACHE_DIR, self.key(text, voice) + "." + self.fmt)
        if os.path.exists(path):
            return open(path, "rb").read(), True      # trúng cache: không tốn token
        data = await self.synth(text, voice, alive)
        tmp = path + ".tmp"; open(tmp, "wb").write(data); os.replace(tmp, path)
        return data, False

class SDKProvider(Provider):
    """VieNeu chạy ngay trong tiến trình (ONNX CPU / CUDA) — không cần server, không tốn token."""
    fmt = "wav"; cloud = False
    def __init__(self):
        self.tts = None; self.err = None; self.ms_per_char = None
        self._load = threading.Lock(); self.lock = asyncio.Lock()

    @property
    def ready(self): return self.tts is not None

    def _ensure(self):
        with self._load:
            if self.tts is None:
                from vieneu import Vieneu
                kw = {}
                if config.SDK_MODE: kw["mode"] = config.SDK_MODE
                if config.SDK_PRECISION: kw["precision"] = config.SDK_PRECISION
                try:
                    tts = Vieneu(**kw)           # lần đầu tải model từ Hugging Face (~vài trăm MB)
                except Exception:
                    if os.environ.pop("HF_HUB_OFFLINE", None) is None: raise
                    tts = Vieneu(**kw)           # cache đóng gói không dùng được → tải từ mạng
                try: tts.infer("Xin chào các bạn.", voice=config.DEFAULT_VOICE)   # chạy thử 1 lần để làm nóng
                except Exception: pass
                self.tts = tts
        return self.tts

    def preload_sync(self):
        try: self._ensure()
        except Exception as e: self.err = f"{e.__class__.__name__}: {e}"

    async def warmup(self):
        await asyncio.to_thread(self.preload_sync)

    def _infer(self, text, voice):
        tts = self._ensure()
        audio = tts.infer(text, voice=voice)
        fd, path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
        try:
            tts.save(audio, path)
            return open(path, "rb").read()
        finally:
            os.remove(path)

    async def synth(self, text, voice, alive=None):
        async with self.lock:                    # model dùng chung: xử lý lần lượt từng đoạn
            if alive and not await alive():      # người nghe đã nhảy đoạn khác → bỏ, nhường chỗ cho đoạn cần
                raise TTSError(499, "Yêu cầu đã huỷ")
            t0 = time.perf_counter()
            try:
                data = await asyncio.to_thread(self._infer, text, voice)
                ms = (time.perf_counter() - t0) * 1000 / max(len(text), 1)
                self.ms_per_char = ms if self.ms_per_char is None else self.ms_per_char * .7 + ms * .3
                return data
            except ImportError: raise TTSError(500, "Chưa cài VieNeu: pip install vieneu")
            except Exception as e: raise TTSError(502, f"VieNeu (local) lỗi: {e}")

    async def voices(self):
        tts = await asyncio.to_thread(self._ensure)
        for name in ("list_preset_voices", "list_voices"):
            f = getattr(tts, name, None)
            if callable(f):
                try:
                    out = []
                    for v in f():
                        if isinstance(v, dict): out.append({"id": str(v.get("id") or v.get("name")), "name": str(v.get("name") or v.get("id"))})
                        elif isinstance(v, (tuple, list)): out.append({"id": str(v[-1]), "name": str(v[0])})
                        else: out.append({"id": str(v), "name": str(v)})
                    if out: return out
                except Exception: pass
        return [{"id": config.DEFAULT_VOICE, "name": config.DEFAULT_VOICE}]

    async def stream(self, text, voice):
        raise TTSError(501, "Chế độ SDK chưa hỗ trợ streaming; dùng /api/tts")

provider = SDKProvider() if config.TTS_PROVIDER == "sdk" else Provider()
