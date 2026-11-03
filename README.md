# VibeRead

## Cho người dùng cuối (không cần gõ lệnh)
1. Nhấp đúp **VibeRead-Setup.exe** → Next → Next → Install → Finish.
2. Mở VibeRead từ Desktop hoặc Start Menu. Dán link truyện và nghe.
Windows có thể hiện "Windows protected your PC" vì bộ cài chưa ký số: bấm **More info → Run anyway**.
Cài theo người dùng, không cần quyền Admin. Gỡ cài ở Settings → Apps. Dữ liệu nghe nằm ở %APPDATA%\VibeRead.

## Cho người build bộ cài (không cần cài gì trên máy)
1. Tạo repo trên github.com, bấm **Add file → Upload files**, kéo toàn bộ nội dung thư mục `viberead` vào (kể cả `.github`).
2. Tab **Actions → Build Windows installer → Run workflow**.
3. Chờ ~15–30 phút, tải **VibeRead-Setup** ở mục Artifacts (file zip chứa bộ cài). Gửi file .exe cho máy khác.
Hoặc trên Windows có Python + Inno Setup 6: nhấp đúp `apps/api/build_windows.bat`.
Phát hành chính thức: tạo tag `v1.0.0` → bộ cài tự đính vào mục Releases.

## Chạy khi phát triển
    cd apps/api && pip install -r requirements-desktop.txt && python desktop.py
Biến tuỳ chọn: TTS_PROVIDER=sdk|local|cloud, VIENEU_MODE=v3nano, VIENEU_PRECISION=int8.
