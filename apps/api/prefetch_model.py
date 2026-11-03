"""Prefetch VieNeu into flat dirs for offline installer (no HF symlink ORT crash)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.makedirs("hf_cache", exist_ok=True)
HF_HOME = os.path.abspath("hf_cache")
os.environ["HF_HOME"] = HF_HOME
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(HF_HOME, "hub")
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ.pop("HF_HUB_OFFLINE", None)
os.environ["APP_DATA"] = HF_HOME

def main() -> int:
    print(f"Prefetch flat models under {HF_HOME} ...")
    try:
        import config
        config.DATA_DIR = HF_HOME
        from tts.model_store import ensure_models, models_root, GRAPH_FILES, onnx_dir

        def prog(s):
            print(s)

        onnx_path, codec_path = ensure_models(progress=prog)
        print("onnx:", onnx_path)
        print("codec:", codec_path)

        from tts.providers import SDKProvider
        p = SDKProvider()
        p._ensure()
        p.tts.infer("Xin chao cac ban.", voice=config.DEFAULT_VOICE)
        print("OK - model verified in", models_root())

        for fn in GRAPH_FILES:
            src = Path(onnx_path) / fn
            if src.is_file():
                dest = Path(HF_HOME) / "hub" / "flat" / fn
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.copy2(src, dest)
        return 0
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        print("WARN: continuing without verified model (use in-app download).", file=sys.stderr)
        return 0

if __name__ == "__main__":
    sys.exit(main())
