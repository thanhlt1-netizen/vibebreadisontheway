"""
Download VieNeu model into ./hf_cache for offline installer bundle.

Windows + recent ONNX Runtime reject HF hub layouts where .onnx and
.external data live in different blob dirs linked by symlinks:
  External data path escapes model directory

Fix: force HF to copy files into snapshot dirs (no symlinks), then
materialize any remaining links so onnx + .data sit side-by-side.
"""
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

# --- HF / ORT path safety (must be set BEFORE huggingface_hub / vieneu import) ---
os.makedirs("hf_cache", exist_ok=True)
HF_HOME = os.path.abspath("hf_cache")
os.environ["HF_HOME"] = HF_HOME
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(HF_HOME, "hub")
# Critical on Windows CI: copy files into snapshots instead of symlinking to blobs/
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ.pop("HF_HUB_OFFLINE", None)


def _materialize_links(root: Path) -> int:
    """Replace symlinks/junctions under root with real file copies (in-place)."""
    fixed = 0
    if not root.is_dir():
        return 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            p = Path(dirpath) / name
            try:
                if p.is_symlink() or os.path.islink(p):
                    target = p.resolve()
                    if target.is_file():
                        p.unlink()
                        shutil.copy2(target, p)
                        fixed += 1
            except OSError:
                continue
    return fixed


def _ensure_onnx_data_colocated(root: Path) -> None:
    """
    If an .onnx references external data via relative name, ensure that
    data file exists next to the .onnx (copy from elsewhere under root if needed).
    """
    for onnx in root.rglob("*.onnx"):
        parent = onnx.parent
        # Common companion names used by VieNeu / ORT
        for cand in (
            "vieneu_backbone_shared.data",
            onnx.name + ".data",
            onnx.stem + ".data",
            "model.onnx_data",
        ):
            dest = parent / cand
            if dest.exists():
                continue
            # search under root
            matches = list(root.rglob(cand))
            if matches:
                try:
                    shutil.copy2(matches[0], dest)
                    print(f"Copied external data -> {dest}")
                except OSError as e:
                    print(f"WARN copy {cand}: {e}")


def main() -> int:
    print(f"Downloading model (HF_HOME={HF_HOME}, HF_HUB_DISABLE_SYMLINKS=1)...")
    try:
        import config
        from vieneu import Vieneu

        tts = Vieneu()
        tts.infer(
            "Xin chao cac ban, day la ban thu giong.",
            voice=config.DEFAULT_VOICE,
        )
        print("OK - model loaded and cached in", HF_HOME)
        return 0
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"First load failed: {msg}", file=sys.stderr)

        # Try materialize + colocated data, then reload once
        root = Path(HF_HOME)
        n = _materialize_links(root)
        print(f"Materialized {n} linked files under {root}")
        _ensure_onnx_data_colocated(root)

        try:
            # Clear any cached module state by re-importing path env
            from vieneu import Vieneu
            import config

            tts = Vieneu()
            tts.infer("Xin chao.", voice=config.DEFAULT_VOICE)
            print("OK after materialize - model in", HF_HOME)
            return 0
        except Exception as e2:
            print(f"ERROR after materialize: {type(e2).__name__}: {e2}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            # Soft-fail: still produce installer; user can download model in-app
            print(
                "WARN: continuing without bundled model "
                "(installer will work; use in-app 'Tai goi giong doc').",
                file=sys.stderr,
            )
            # Leave partial cache; do not fail the whole CI job
            return 0


if __name__ == "__main__":
    sys.exit(main())
