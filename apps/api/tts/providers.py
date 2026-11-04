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
        from tts.model_store import onnx_dir, _ready, GRAPH_FILES
        od = onnx_dir()
        cached = _ready(od, GRAPH_FILES)
        return {
            "ready": self.ready,
            "error": self.err,
            "downloading": self.downloading,
            "download_msg": self.download_msg,
            "hf_home": os.environ.get("HF_HOME", ""),
            "bundled_or_cached": cached,
            "onnx_dir": str(od),
            "ms_per_char": self.ms_per_char,
        }

    def _make_tts(self, onnx_path: str, codec_path: str, precision: str = "fp32"):
        """Load VieNeu with flat onnx_dir + codec_dir (avoids HF symlink/ORT bug)."""
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

        import vieneu._v3_turbo_engine.onnx_runtime_lite as lite
        _orig_init = lite.OnnxV3LiteEngine.__init__

        def _patched_init(self, *args, **kwargs):
            kwargs["onnx_dir"] = onnx_path
            kwargs["codec_dir"] = codec_path
            return _orig_init(self, *args, **kwargs)

        lite.OnnxV3LiteEngine.__init__ = _patched_init
        try:
            from vieneu import Vieneu
            prec = precision or "fp32"
            kw = {"backend": "onnx", "onnx_dir": onnx_path, "precision": prec}
            if config.SDK_MODE:
                kw["mode"] = config.SDK_MODE
            if getattr(config, "SDK_THREADS", 0):
                kw["threads"] = config.SDK_THREADS
            try:
                return Vieneu(**kw)
            except Exception:
                if prec != "fp32":
                    kw["precision"] = "fp32"
                    return Vieneu(**kw)
                raise
        finally:
            lite.OnnxV3LiteEngine.__init__ = _orig_init

    def _smoke(self, tts) -> None:
        """Must produce audio or we reject the session."""
        last = None
        for voice in (None, config.DEFAULT_VOICE, "Hải Đăng"):
            try:
                if voice:
                    tts.infer("Xin chao.", voice=voice)
                else:
                    tts.infer("Xin chao.")
                return
            except Exception as e:
                last = e
        raise RuntimeError(f"Smoke infer failed: {last}") from last

    def _ensure(self):
        with self._load:
            if self.tts is not None:
                return self.tts
            self.downloading = True
            self.download_msg = "Dang nap model..."
            try:
                from tts.model_store import (
                    ensure_models, seed_from_bundle, diagnose, prefer_onnx_dir, force_repair,
                )
                from pathlib import Path

                for cand in (
                    Path(os.environ.get("VIBEREAD_BUNDLE_HF", "")),
                    Path(os.environ.get("HF_HOME", "")),
                    Path(getattr(__import__("sys"), "_MEIPASS", ".")) / "hf_cache",
                ):
                    try:
                        if cand.is_dir():
                            seed_from_bundle(cand)
                    except Exception:
                        pass

                def prog(s):
                    self.download_msg = s

                # Always load fp32 flat dir unless user forces int8 AND files ready
                want8 = (config.SDK_PRECISION or "fp32").lower() == "int8"
                onnx_path, codec_path = ensure_models(progress=prog)
                if want8:
                    onnx_path = prefer_onnx_dir(want_int8=True) or onnx_path
                else:
                    onnx_path = prefer_onnx_dir(want_int8=False)

                diag = diagnose()
                # If using onnx/ but missing files listed relative to that folder
                from tts.model_store import onnx_dir, missing_files, GRAPH_FILES
                miss = missing_files(Path(onnx_path), GRAPH_FILES)
                if miss or diag["codec_missing"]:
                    raise FileNotFoundError(
                        "Thieu file model: "
                        + ", ".join(miss + diag["codec_missing"])
                        + f" (onnx={onnx_path})"
                    )

                prec = "int8" if (want8 and "onnx_int8" in onnx_path.replace("\\", "/")) else "fp32"
                tts = self._make_tts(onnx_path, codec_path, precision=prec)
                try:
                    self._smoke(tts)
                except Exception as e1:
                    # Corrupt cache → repair once then reload
                    msg = str(e1).lower()
                    if "file" in msg or "os error" in msg or "onnx" in msg:
                        self.download_msg = "Cache loi, dang tai lai model..."
                        force_repair()
                        onnx_path, codec_path = ensure_models(progress=prog)
                        tts = self._make_tts(onnx_path, codec_path, precision="fp32")
                        self._smoke(tts)
                    else:
                        raise
                self.tts = tts
                self.err = None
                self.download_msg = "Model san sang"
                return self.tts
            except Exception as e:
                self.tts = None
                self.err = f"{e.__class__.__name__}: {e}"
                self.download_msg = f"Loi: {self.err}"
                raise
            finally:
                self.downloading = False
        return self.tts

    def preload_sync(self):
        try:
            self._ensure()
        except Exception as e:
            self.err = f"{e.__class__.__name__}: {e}"

    def download_model_sync(self):
        """Manual download into flat APPDATA dirs, then load (fp32)."""
        if self.downloading:
            return False, "Dang tai model..."
        self.downloading = True
        self.download_msg = "Dang tai model giong doc (co the vai phut)..."
        self.err = None
        try:
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
            from tts.model_store import ensure_models, models_root, force_repair

            force_repair()

            def prog(s):
                self.download_msg = s

            onnx_path, codec_path = ensure_models(progress=prog)
            with self._load:
                self.tts = None
                self.tts = self._make_tts(onnx_path, codec_path, precision="fp32")
                self._smoke(self.tts)
                self.err = None
            self.download_msg = f"Da tai xong model ({models_root()})"
            return True, "OK"
        except Exception as e:
            self.err = f"{e.__class__.__name__}: {e}"
            self.download_msg = f"Loi: {self.err}"
            self.tts = None
            return False, self.err
        finally:
            self.downloading = False

    async def warmup(self):
        await asyncio.to_thread(self.preload_sync)

    async def download_model(self):
        return await asyncio.to_thread(self.download_model_sync)

    def _audio_to_wav_bytes(self, tts, audio) -> bytes:
        """In-memory WAV — avoids disk I/O on every segment."""
        import io
        import numpy as np
        try:
            import soundfile as sf
            buf = io.BytesIO()
            sf.write(buf, np.asarray(audio), int(getattr(tts, "sample_rate", 48000) or 48000), format="WAV")
            return buf.getvalue()
        except Exception:
            # Fallback: temp under DATA_DIR
            out_dir = os.path.join(config.DATA_DIR, "audio", "tmp")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"t{os.getpid()}_{time.time_ns()}.wav")
            try:
                tts.save(audio, path)
                with open(path, "rb") as f:
                    return f.read()
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _infer_once(self, tts, text, voice):
        from textutil import for_tts
        clean = for_tts(text)
        # Prefer no voice kw if default — some builds look for missing ref files
        try:
            if voice:
                audio = tts.infer(clean, voice=voice)
            else:
                audio = tts.infer(clean)
        except TypeError:
            audio = tts.infer(clean, voice=voice or config.DEFAULT_VOICE)
        return self._audio_to_wav_bytes(tts, audio)

    def _reset_engine(self):
        """Drop broken ONNX session so next _ensure reloads graphs."""
        with self._load:
            self.tts = None
            self.err = None

    def _infer(self, text, voice):
        # Caller already holds asyncio lock; only serialize vs preload thread
        voice = (voice or config.DEFAULT_VOICE or "").strip() or config.DEFAULT_VOICE
        text = (text or "").strip()
        if len(text) < 2:
            text = text + " ."
        last = None
        voices_try = [voice]
        if voice not in ("Hải Đăng", "Hai Dang", "Hải Đăng"):
            voices_try.append("Hải Đăng")
        # empty voice = package default
        voices_try.append("")

        for attempt in range(4):
            try:
                tts = self._ensure()
                with self._load:
                    return self._infer_once(tts, text, voices_try[min(attempt, len(voices_try) - 1)])
            except Exception as e:
                last = e
                msg = str(e).lower()
                missing = (
                    "os error 2" in msg
                    or "cannot find the file" in msg
                    or "filenotfound" in e.__class__.__name__.lower()
                    or "no such file" in msg
                )
                if missing:
                    # Only hard-reset once per call; prefer retry same session first
                    if attempt == 2:
                        self._reset_engine()
                    time.sleep(0.3 * (attempt + 1))
                    continue
                # Non-file errors: try alternate voice once
                if attempt == 0 and len(voices_try) > 1:
                    continue
                break

        # Last resort: split long text and synth first half (keeps playback alive)
        if last and len(text) > 80:
            try:
                cut = max(text.rfind(" ", 0, len(text) // 2), len(text) // 3)
                half = text[:cut].strip()
                if half:
                    tts = self._ensure()
                    with self._load:
                        return self._infer_once(tts, half, "Hải Đăng")
            except Exception as e2:
                last = e2

        raise RuntimeError(f"infer failed after retries: {last}") from last

    async def synth(self, text, voice, alive=None):
        if self.downloading:
            raise TTSError(503, "Dang nap/tai model giọng đọc — doi 30-60s roi bam nghe lai")
        if self.err and self.tts is None:
            raise TTSError(503, f"Model chua san sang: {self.err}. Mo Cai dat → Tai goi giong doc")
        async with self.lock:
            if alive and not await alive():
                raise TTSError(499, "Yeu cau da huy")
            t0 = time.perf_counter()
            try:
                data = await asyncio.to_thread(self._infer, text, voice)
                # transient segment failure must NOT mark whole engine dead
                if self.tts is not None:
                    self.err = None
                ms = (time.perf_counter() - t0) * 1000 / max(len(text), 1)
                self.ms_per_char = ms if self.ms_per_char is None else self.ms_per_char * 0.7 + ms * 0.3
                return data
            except TTSError:
                raise
            except ImportError:
                raise TTSError(500, "Chua cai VieNeu: pip install vieneu")
            except Exception as e:
                msg = f"{e.__class__.__name__}: {e}"
                # keep engine; only report segment error
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
