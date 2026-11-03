import os
def env(k, d=""): return os.getenv(k, d)
TTS_PROVIDER = env("TTS_PROVIDER", "sdk")   # sdk = VieNeu chạy trong tiến trình | local = server OpenAI-compatible | cloud
CLOUD_URL = env("VIENEU_CLOUD_URL", "https://api.vieneu.io/api/v1")
LOCAL_URL = env("VIENEU_LOCAL_URL", "http://localhost:8000/v1")
LOCAL_MODEL = env("VIENEU_LOCAL_MODEL", "vieneu-v3-turbo")
API_KEY = env("VIENEU_API_KEY")
DEFAULT_VOICE = env("DEFAULT_VOICE", "Ngọc Lan" if TTS_PROVIDER == "cloud" else "Minh Quân Pro")
CORS = env("CORS_ORIGINS", "http://localhost:3000").split(",")
import sys
def _data_dir():
    if env("APP_DATA"): return env("APP_DATA")
    if sys.platform == "win32": base = env("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin": base = os.path.expanduser("~/Library/Application Support")
    else: base = env("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(base, "VibeRead")
DATA_DIR = _data_dir()
CACHE_DIR = env("AUDIO_CACHE_DIR", os.path.join(DATA_DIR, "audio"))
SDK_MODE = env("VIENEU_MODE")             # để trống = v3 Turbo; "v3nano" cho máy yếu
SDK_PRECISION = env("VIENEU_PRECISION")   # "int8" nhanh hơn ~1.6x nếu CPU có VNNI
MIN_CHARS = 50 if TTS_PROVIDER == "cloud" else 20          # Cloud API: tối thiểu 50 ký tự mỗi request
ANTHROPIC_KEY = env("ANTHROPIC_API_KEY")
TRANSLATE_MODEL = env("TRANSLATE_MODEL", "claude-sonnet-5-5")
MAX_PREFETCH_CHARS = int(env("MAX_PREFETCH_CHARS", "30000"))   # chặn tải trước chương quá dài (tốn token Cloud)
