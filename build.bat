@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo        YVmonitor Build Pipeline
echo ========================================

:: ===== 0. 环境检查 =====
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js not found. Please install Node.js first.
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found.
  exit /b 1
)

:: ===== 1. 构建前端 =====
echo.
echo [1/4] Building frontend...

cd frontend

if not exist node_modules (
  echo Installing frontend dependencies...
  call npm install
)

echo Running build...
call npm run build
if errorlevel 1 (
  echo [ERROR] Frontend build failed.
  exit /b 1
)

cd ..

:: ===== 2. 同步到 backend =====
echo.
echo [2/4] Syncing frontend to backend...

if exist "backend\static" (
  rmdir /s /q "backend\static"
)

xcopy /E /I /Y "frontend\dist" "backend\static" >nul
if errorlevel 1 (
  echo [ERROR] Failed to copy frontend dist.
  exit /b 1
)

:: ===== 3. 清理旧构建 =====
echo.
echo [3/4] Cleaning old build artifacts...

if exist "build" rmdir /s /q "build"
if exist "dist\YVmonitor.exe" del /q "dist\YVmonitor.exe"

:: ===== 4. 打包 exe =====
echo.
echo [4/4] Building executable...

python -m pip install -q pyinstaller

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
  echo [ERROR] Build failed.
  exit /b 1
)

:: ===== 完成 =====
echo.
echo ========================================
echo  Build Success: dist\YVmonitor.exe
echo ========================================
pause
exit /b 0