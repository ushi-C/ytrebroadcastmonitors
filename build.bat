@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo        YVmonitor Build Pipeline
echo ========================================

:: ===== 0. Environment check =====
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js not found
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found
  exit /b 1
)

:: ===== 1. Frontend build =====
echo.
echo [1/4] Building frontend...

cd frontend

if not exist node_modules (
  echo Installing dependencies...
  call npm install
)

call npm run build
if errorlevel 1 (
  echo [ERROR] Frontend build failed
  exit /b 1
)

cd ..

:: ===== 2. Sync static =====
echo.
echo [2/4] Syncing frontend to backend...

if exist backend\static (
  rmdir /s /q backend\static
)

xcopy /E /I /Y frontend\dist backend\static >nul

if errorlevel 1 (
  echo [ERROR] Failed to copy frontend dist.
  exit /b 1
)

:: ===== 3. Clean =====
echo.
echo [3/4] Cleaning...

if exist build rmdir /s /q build
if exist dist\YVmonitor.exe del /q dist\YVmonitor.exe

:: ===== 4. PyInstaller =====
echo.
echo [4/4] Building EXE...

python -m pip install -q pyinstaller

pyinstaller --noconfirm --clean --onefile --windowed --name YVmonitor ^
  --icon icon.ico ^
  --add-data "backend/static;static" ^
  --version-file version_info.txt ^
  --add-data "icon.ico;." ^
  --collect-all yt_dlp ^
  --collect-all webview ^
  "%~dp0backend\main.py"

if errorlevel 1 (
  echo [ERROR] Build failed
  exit /b 1
)

echo.
echo ========================================
echo SUCCESS: dist\YVmonitor.exe
echo ========================================
pause
exit /b 0
