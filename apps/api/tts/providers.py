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
    """VieNeu in-process (ONNX). No server, no cloud tokens."""
    fmt = "wav"
    cloud = False

    def __init__(self):
        self.tts = None
        self.err = None
        self.ms_per_char = None
        self._load = threading.Lock()
        self.lock = asyncio.Lock()
        self.downloading = False
        self.download_msg = ""

    @property
    def ready(self):
        return self.tts is not None

    def status(self) -> dict:
        hf = os.environ.get("HF_HOME", "")
        bundled = bool(hf and os.path.isdir(hf) and any(
            p.endswith((".onnx", ".bin", ".safetensors", ".json"))
            for r, _, files in os.walk(hf) for p in files
        )) if hf and os.path.isdir(hf) else False
        return {
            "ready": self.ready,
            "error": self.err,
            "downloading": self.downloading,
            "download_msg": self.download_msg,
            "hf_home": hf,
            "bundled_or_cached": bundled,
            "ms_per_char": self.ms_per_char,
        }

    def _ensure(self):
        with self._load:
            if self.tts is None:
                from vieneu import Vieneu
                kw = {}
                if config.SDK_MODE:
                    kw["mode"] = config.SDK_MODE
                if config.SDK_PRECISION:
                    kw["precision"] = config.SDK_PRECISION
                # Allow retry from network if offline flag was set from a bad bundle path
                try:
                    tts = Vieneu(**kw)
                except Exception:
                    if os.environ.pop("HF_HUB_OFFLINE", None) is None:
                        raise
                    tts = Vieneu(**kw)
                try:
                    tts.infer("Xin chao cac ban.", voice=config.DEFAULT_VOICE)
                except Exception:
                    pass
                self.tts = tts
                self.err = None
        return self.tts

    def preload_sync(self):
        try:
            self._ensure()
        except Exception as e:
            self.err = f"{e.__class__.__name__}: {e}"

    def download_model_sync(self):
        """Manual / first-run model fetch into HF_HOME (writable)."""
        if self.downloading:
            return False, "Dang tai model..."
        self.downloading = True
        self.download_msg = "Dang tai model giọng đọc (có thể vài phút)..."
        self.err = None
        try:
            # Force online
            os.environ.pop("HF_HUB_OFFLINE", None)
            # Reset instance so _ensure reloads
            with self._load:
                self.tts = None
            self._ensure()
            self.download_msg = "Da tai xong model"
            return True, "OK"
        except Exception as e:
            self.err = f"{e.__class__.__name__}: {e}"
            self.download_msg = f"Loi: {self.err}"
            return False, self.err
        finally:
            self.downloading = False

    async def warmup(self):
        await asyncio.to_thread(self.preload_sync)

    async def download_model(self):
        return await asyncio.to_thread(self.download_model_sync)

    def _infer(self, text, voice):
        tts = self._ensure()
        audio = tts.infer(text, voice=voice)
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            tts.save(audio, path)
            with open(path, "rb") as f:
                return f.read()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    async def synth(self, text, voice, alive=None):
        async with self.lock:
            if alive and not await alive():
                raise TTSError(499, "Yeu cau da huy")
            t0 = time.perf_counter()
            try:
                data = await asyncio.to_thread(self._infer, text, voice)
                ms = (time.perf_counter() - t0) * 1000 / max(len(text), 1)
                self.ms_per_char = ms if self.ms_per_char is None else self.ms_per_char * 0.7 + ms * 0.3
                return data
            except ImportError:
                raise TTSError(500, "Chua cai VieNeu: pip install vieneu")
            except Exception as e:
                msg = f"{e.__class__.__name__}: {e}"
                self.err = msg
                raise TTSError(500, f"VieNeu (local) loi: {e}")

    async def cached(self, text, voice, alive=None):
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        path = os.path.join(config.CACHE_DIR, self.key(text, voice) + "." + self.fmt)
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read(), True
        data = await self.synth(text, voice, alive)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return data, False

    async def voices(self):
        try:
            tts = await asyncio.to_thread(self._ensure)
        except Exception as e:
            self.err = f"{e.__class__.__name__}: {e}"
            return [{"id": config.DEFAULT_VOICE, "name": config.DEFAULT_VOICE}]
        for name in ("voices", "list_voices"):
            f = getattr(tts, name, None)
            if callable(f):
                try:
                    out = []
                    for v in f():
                        if isinstance(v, dict):
                            out.append({"id": str(v.get("id") or v.get("name")), "name": str(v.get("name") or v.get("id"))})
                        elif isinstance(v, (tuple, list)):
                            out.append({"id": str(v[-1]), "name": str(v[0])})
                        else:
                            out.append({"id": str(v), "name": str(v)})
                    if out:
                        return out
                except Exception:
                    pass
        return [{"id": config.DEFAULT_VOICE, "name": config.DEFAULT_VOICE}]

    async def stream(self, text, voice):
        raise TTSError(501, "Che do SDK chua ho tro streaming; dung /api/tts")


provider = SDKProvider() if config.TTS_PROVIDER == "sdk" else Provider()
