"""VibeRead Desktop: native window + backend + VieNeu in-process."""
import os, socket, sys, threading, time
from pathlib import Path

os.environ.setdefault("TTS_PROVIDER", "sdk")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--autoplay-policy=no-user-gesture-required")

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

# Prefer bundled model; otherwise use writable APPDATA cache so first-run / manual download works
if (BASE / "hf_cache").is_dir():
    os.environ.setdefault("HF_HOME", str(BASE / "hf_cache"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
else:
    # Must be set BEFORE importing config/vieneu so downloads go to a writable place
    _appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    _hf = os.path.join(_appdata, "VibeRead", "hf_cache")
    os.makedirs(_hf, exist_ok=True)
    os.environ.setdefault("HF_HOME", _hf)
    # Allow network download when model not bundled
    os.environ.pop("HF_HUB_OFFLINE", None)

os.chdir(BASE)

import config
os.makedirs(config.DATA_DIR, exist_ok=True)
LOG = os.path.join(config.DATA_DIR, "viberead.log")
if sys.stdout is None or sys.stderr is None or getattr(sys, "frozen", False):
    _f = open(LOG, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _f
    sys.stderr = sys.stderr or _f

PORT = 18765

def pick_port() -> int:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", PORT))
            return PORT
        except OSError:
            s2 = socket.socket()
            s2.bind(("127.0.0.1", 0))
            p = s2.getsockname()[1]
            s2.close()
            return p

def alert(msg: str):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "VibeRead", 0x10)
    except Exception:
        print(msg)

def main():
    import uvicorn, webview
    from main import app
    from tts.providers import provider
    if config.TTS_PROVIDER == "sdk":
        threading.Thread(target=provider.preload_sync, daemon=True).start()
    port = pick_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    webview.create_window(
        "VibeRead",
        f"http://127.0.0.1:{port}/",
        width=1120,
        height=780,
        min_size=(380, 600),
        background_color="#0c0f12",
    )
    webview.start(private_mode=False, storage_path=os.path.join(config.DATA_DIR, "webview"))
    server.should_exit = True

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        alert(f"VibeRead gap loi khi khoi dong:\n{e}\n\nChi tiet: {LOG}")
