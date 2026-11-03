"""Tải model VieNeu vào ./hf_cache để đóng gói sẵn trong bộ cài (người dùng khỏi phải tải lần đầu)."""
import os
import sys

os.makedirs("hf_cache", exist_ok=True)
os.environ["HF_HOME"] = os.path.abspath("hf_cache")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

try:
    import config
    from vieneu import Vieneu
    print(f"Đang tải model (HF_HOME={os.environ['HF_HOME']})...")
    tts = Vieneu()
    tts.infer("Xin chào các bạn, đây là bản thử giọng.", voice=config.DEFAULT_VOICE)
    print("OK — model đã nằm trong", os.environ["HF_HOME"])
except Exception as e:
    print(f"LỖI khi tải model: {type(e).__name__}: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
