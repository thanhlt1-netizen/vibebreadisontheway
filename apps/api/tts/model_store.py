"""
Download VieNeu ONNX graphs + codec into flat local dirs.

Why: HuggingFace hub cache uses content-addressed blobs + symlinks.
Recent ONNX Runtime rejects external .data files that resolve outside the
.onnx directory ("External data path escapes model directory"). Putting
every file as a real copy in one folder fixes that on Windows and in
PyInstaller bundles.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import config

# Keep in sync with vieneu._v3_turbo_engine.onnx_runtime_lite
V3_REPO = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
CODEC_REPO = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"
ONNX_SUBFOLDER = "onnx_update"  # fp32

GRAPH_FILES = [
    "vieneu_prefill.onnx",
    "vieneu_decode_step.onnx",
    "vieneu_acoustic_cached.onnx",
    "vieneu_backbone_shared.data",
    "vieneu_v3_heads.npz",
    "config.json",
    "tokenizer.json",
]
CODEC_FILES = [
    "moss_audio_tokenizer_decode_full.onnx",
    "moss_audio_tokenizer_decode_shared.data",
    "moss_audio_tokenizer_decode_step.onnx",
    "codec_browser_onnx_meta.json",
    "moss_audio_tokenizer_encode.onnx",
    "moss_audio_tokenizer_encode.data",
]
# Optional cloning helpers (repo root)
ROOT_FILES = ["denoiser.onnx", "speaker_encoder.onnx", "voices_v3_turbo.json"]

MARKER = ".viberead_ready"


def models_root() -> Path:
    root = Path(config.DATA_DIR) / "vieneu_models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def onnx_dir() -> Path:
    return models_root() / "onnx"


def codec_dir() -> Path:
    return models_root() / "codec"


def missing_files(d: Path, required: list[str]) -> list[str]:
    out = []
    for f in required:
        p = d / f
        if not p.is_file() or p.stat().st_size == 0:
            out.append(f)
    return out


def _ready(d: Path, required: list[str]) -> bool:
    if not (d / MARKER).is_file():
        return False
    return not missing_files(d, required)


def diagnose() -> dict:
    od, cd = onnx_dir(), codec_dir()
    need_codec = [f for f in CODEC_FILES if not f.endswith(".json")]
    return {
        "onnx_dir": str(od),
        "codec_dir": str(cd),
        "onnx_ready": _ready(od, GRAPH_FILES),
        "codec_ready": _ready(cd, need_codec),
        "onnx_missing": missing_files(od, GRAPH_FILES),
        "codec_missing": missing_files(cd, need_codec),
        "marker_onnx": (od / MARKER).is_file(),
        "marker_codec": (cd / MARKER).is_file(),
    }


def _download_one(repo: str, filename: str, dest: Path, subfolder: str | None) -> None:
    from huggingface_hub import hf_hub_download

    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    src = hf_hub_download(
        repo_id=repo,
        filename=filename,
        repo_type="model",
        subfolder=subfolder,
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Always real file copy (no symlink into hub blobs)
    if dest.exists():
        dest.unlink()
    shutil.copy2(src, dest)


def ensure_models(progress=None) -> tuple[str, str]:
    """
    Ensure flat onnx + codec dirs exist. Returns (onnx_dir, codec_dir).
    progress: optional callable(str) for UI status.
    """
    def msg(s: str):
        if progress:
            progress(s)

    od, cd = onnx_dir(), codec_dir()
    od.mkdir(parents=True, exist_ok=True)
    cd.mkdir(parents=True, exist_ok=True)

    if _ready(od, GRAPH_FILES) and _ready(cd, [f for f in CODEC_FILES if not f.endswith(".json")]):
        msg("Model da san sang")
        return str(od), str(cd)

    total = len(GRAPH_FILES) + len(CODEC_FILES) + len(ROOT_FILES)
    done = 0

    for fn in GRAPH_FILES:
        done += 1
        msg(f"Tai backbone {done}/{total}: {fn}")
        if not (od / fn).is_file() or (od / fn).stat().st_size == 0:
            _download_one(V3_REPO, fn, od / fn, ONNX_SUBFOLDER)

    for fn in CODEC_FILES:
        done += 1
        msg(f"Tai codec {done}/{total}: {fn}")
        try:
            if not (cd / fn).is_file() or (cd / fn).stat().st_size == 0:
                _download_one(CODEC_REPO, fn, cd / fn, None)
        except Exception as e:
            # meta json optional
            if fn.endswith(".json"):
                msg(f"Bo qua {fn}: {e}")
                continue
            raise

    for fn in ROOT_FILES:
        done += 1
        msg(f"Tai phu {done}/{total}: {fn}")
        try:
            if not (od / fn).is_file():
                _download_one(V3_REPO, fn, od / fn, None)
        except Exception:
            pass  # optional

    (od / MARKER).write_text("ok", encoding="utf-8")
    (cd / MARKER).write_text("ok", encoding="utf-8")
    msg("Hoan tat tai model")
    return str(od), str(cd)


def seed_from_bundle(bundle_hf: Path) -> bool:
    """
    If installer shipped a usable hf_cache, try to copy onnx graphs into flat dirs.
    Returns True if onnx dir looks ready after copy.
    """
    if not bundle_hf.is_dir():
        return False
    od = onnx_dir()
    od.mkdir(parents=True, exist_ok=True)
    copied = 0
    for fn in GRAPH_FILES:
        if (od / fn).is_file():
            continue
        matches = list(bundle_hf.rglob(fn))
        if matches:
            shutil.copy2(matches[0], od / fn)
            copied += 1
    if all((od / f).is_file() for f in GRAPH_FILES):
        (od / MARKER).write_text("ok", encoding="utf-8")
        return True
    return copied > 0
