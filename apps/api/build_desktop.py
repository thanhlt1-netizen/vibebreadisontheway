"""Đóng gói app: python build_desktop.py → dist/VibeRead (thư mục, khởi động nhanh hơn 1 file)."""
import os
import sys
import PyInstaller.__main__ as pi

os.makedirs("assets", exist_ok=True)
os.makedirs("dist", exist_ok=True)

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
    args += ["--add-data", f"hf_cache{sep}hf_cache"]  # model đóng gói sẵn
    print("Đóng gói kèm model hf_cache")
else:
    print("Không có hf_cache — bản cài sẽ tải model lần đầu khi chạy")

print("PyInstaller args:", " ".join(args))
try:
    pi.run(args)
except SystemExit as e:
    if e.code not in (0, None):
        raise
print("PyInstaller xong. Kiểm tra dist/VibeRead...")
if not os.path.isdir("dist/VibeRead"):
    print("LỖI: không tìm thấy dist/VibeRead sau khi build", file=sys.stderr)
    sys.exit(1)
print("OK — dist/VibeRead đã sẵn sàng")
