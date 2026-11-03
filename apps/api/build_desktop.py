"""Đóng gói app: python build_desktop.py → dist/VibeRead (thư mục, khởi động nhanh hơn 1 file)."""
import os, PyInstaller.__main__ as pi
sep = ";" if os.name == "nt" else ":"
args = ["desktop.py", "--noconfirm", "--clean", "--name", "VibeRead", "--windowed", "--noupx",
        "--add-data", f"static{sep}static",
        "--collect-all", "vieneu", "--collect-all", "onnxruntime", "--collect-all", "webview",
        "--collect-submodules", "uvicorn",
        "--hidden-import", "uvicorn.logging", "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto", "--hidden-import", "uvicorn.lifespan.on"]
if os.path.exists("assets/icon.ico"): args += ["--icon", "assets/icon.ico"]
if os.path.isdir("hf_cache"): args += ["--add-data", f"hf_cache{sep}hf_cache"]   # model đóng gói sẵn
pi.run(args)
