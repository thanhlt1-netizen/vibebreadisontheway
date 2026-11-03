"""VibeRead Desktop: cửa sổ native + backend + VieNeu chạy local trong cùng một tiến trình."""
import os, socket, sys, threading, time
from pathlib import Path

os.environ.setdefault("TTS_PROVIDER", "sdk")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# tự phát chương sau không cần bấm tay (WebView2 mặc định chặn autoplay)
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--autoplay-policy=no-user-gesture-required")
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if (BASE / "hf_cache").is_dir():                       # model được đóng gói sẵn trong bộ cài → chạy offline
    os.environ.setdefault("HF_HOME", str(BASE / "hf_cache"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.chdir(BASE)

import config
os.makedirs(config.DATA_DIR, exist_ok=True)
LOG = os.path.join(config.DATA_DIR, "viberead.log")
if sys.stdout is None or sys.stderr is None or getattr(sys, "frozen", False):   # --windowed không có console
    _f = open(LOG, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _f; sys.stderr = sys.stderr or _f

PORT = 18765          # CỐ ĐỊNH: IndexedDB/cài đặt của trình duyệt gắn với cổng; đổi cổng là mất tiến độ nghe

def pick_port() -> int:
    with socket.socket() as s:
        try: s.bind(("127.0.0.1", PORT)); return PORT
        except OSError:
            s2 = socket.socket(); s2.bind(("127.0.0.1", 0)); p = s2.getsockname()[1]; s2.close(); return p

def alert(msg: str):
    try:
        import ctypes; ctypes.windll.user32.MessageBoxW(0, msg, "VibeRead", 0x10)
    except Exception: print(msg)

def main():
    import uvicorn, webview
    from main import app
    from tts.providers import provider
    if config.TTS_PROVIDER == "sdk":
        threading.Thread(target=provider.preload_sync, daemon=True).start()     # nạp giọng đọc ngay từ đầu
    port = pick_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started: break
        time.sleep(0.1)
    webview.create_window("VibeRead", f"http://127.0.0.1:{port}/", width=1120, height=780,
                          min_size=(380, 600), background_color="#0c0f12")
    webview.start(private_mode=False, storage_path=os.path.join(config.DATA_DIR, "webview"))
    server.should_exit = True

if __name__ == "__main__":
    try: main()
    except Exception as e:
        import traceback; traceback.print_exc()
        alert(f"VibeRead gặp lỗi khi khởi động:\n{e}\n\nChi tiết: {LOG}")
