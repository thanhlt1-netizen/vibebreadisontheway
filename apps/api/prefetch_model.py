"""Download VieNeu model into ./hf_cache for offline installer bundle."""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.makedirs("hf_cache", exist_ok=True)
os.environ["HF_HOME"] = os.path.abspath("hf_cache")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

try:
    import config
    from vieneu import Vieneu
    print(f"Downloading model (HF_HOME={os.environ['HF_HOME']})...")
    tts = Vieneu()
    tts.infer("Xin chao cac ban, day la ban thu giong.", voice=config.DEFAULT_VOICE)
    print("OK - model in", os.environ["HF_HOME"])
except Exception as e:
    print(f"ERROR loading model: {type(e).__name__}: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
