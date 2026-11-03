@echo off
REM Nhấp đúp để tự build bộ cài trên Windows (cần Python 3.10+ và Inno Setup 6 đã cài). Kết quả: dist-installer\VibeRead-Setup.exe
cd /d "%~dp0"
python -m venv .venv || goto :err
call .venv\Scripts\activate
pip install -r requirements-desktop.txt pillow || goto :err
python make_icon.py || goto :err
if not exist hf_cache python prefetch_model.py
python build_desktop.py || goto :err
if not exist installer\MicrosoftEdgeWebview2Setup.exe powershell -Command "Invoke-WebRequest https://go.microsoft.com/fwlink/p/?LinkId=2124703 -OutFile installer\MicrosoftEdgeWebview2Setup.exe"
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer\VibeRead.iss || goto :err
echo. & echo XONG: dist-installer\VibeRead-Setup.exe & pause & exit /b 0
:err
echo LOI - xem thong bao phia tren & pause & exit /b 1
