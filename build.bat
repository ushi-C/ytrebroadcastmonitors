@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Cleaning previous build artifacts...
if exist "build" rmdir /s /q "build"
if exist "dist\YVmonitor.exe" del /q "dist\YVmonitor.exe"

echo Installing build deps...
python -m pip install -q -r requirements.txt pyinstaller

echo Building YVmonitor.exe ...
pyinstaller --noconfirm --clean --onefile --windowed --name YVmonitor ^
  --icon "icon.ico" ^
  --add-data "backend/static;static" ^
  --add-data "icon.ico;." ^
  --collect-all yt_dlp ^
  --collect-all webview ^
  --hidden-import=backend.utils.config_manager ^
  --hidden-import=backend.cache.avatar_cache ^
  --hidden-import=backend.services.scanner ^
  --hidden-import=backend.api.api ^
  --hidden-import=uvicorn.protocols.http.auto ^
  --hidden-import=uvicorn.protocols.websockets.auto ^
  --hidden-import=uvicorn.loops.auto ^
  --hidden-import=uvicorn.logging ^
  "%~dp0backend\main.py"

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Done: dist\YVmonitor.exe
echo You can now run build_installer.bat to create setup.exe with uninstall support.
exit /b 0
