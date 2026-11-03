"""Build desktop app: python build_desktop.py -> dist/VibeRead"""
import os
import sys

# Force UTF-8 on Windows runners (default cp1252 breaks Vietnamese prints)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.makedirs("assets", exist_ok=True)
os.makedirs("dist", exist_ok=True)

import PyInstaller.__main__ as pi

sep = ";" if os.name == "nt" else ":"
args = [
    "desktop.py",
    "--noconfirm",
    "--clean",
    "--name", "VibeRead",
    "--windowed",
    "--noupx",
    "--add-data", f"static{sep}static",
    "--collect-all", "vieneu",
    "--collect-all", "onnxruntime",
    "--collect-all", "webview",
    "--collect-submodules", "uvicorn",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.lifespan.on",
]
if os.path.exists("assets/icon.ico"):
    args += ["--icon", "assets/icon.ico"]
if os.path.isdir("hf_cache"):
    args += ["--add-data", f"hf_cache{sep}hf_cache"]
    print("Bundling hf_cache model")
else:
    print("No hf_cache - first-run model download")

print("PyInstaller args:", " ".join(args))
try:
    pi.run(args)
except SystemExit as e:
    if e.code not in (0, None):
        raise

if not os.path.isdir("dist/VibeRead"):
    print("ERROR: dist/VibeRead not found after PyInstaller", file=sys.stderr)
    sys.exit(1)
print("OK - dist/VibeRead ready")
