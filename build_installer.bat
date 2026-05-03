@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo     YVmonitor Installer Build
echo ========================================

:: ===== 1. Build EXE =====
echo.
echo [1/2] Building core executable...

call build.bat
if errorlevel 1 (
  echo [ERROR] Core build failed.
  exit /b 1
)

if not exist "dist\YVmonitor.exe" (
  echo [ERROR] EXE not found after build.
  exit /b 1
)

:: ===== 2. Locate Inno Setup =====
echo.
echo [2/2] Locating Inno Setup compiler...

set "ISCC_CMD="

:: Check PATH first
where iscc >nul 2>nul
if not errorlevel 1 (
  set "ISCC_CMD=iscc"
  goto :build
)

:: Common installation paths
for %%P in (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
  "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
) do (
  if exist "%%~P" (
    set "ISCC_CMD=%%~P"
    goto :build
  )
)

echo [ERROR] Inno Setup compiler not found.
echo Please install Inno Setup 6.
exit /b 1

:build
echo Using ISCC: %ISCC_CMD%

:: Default install directory
set "APP_DEFAULT_DIR={autopf}\YVmonitor"

echo Installer target directory: %APP_DEFAULT_DIR%

"%ISCC_CMD%" /DMyAppDefaultDir="%APP_DEFAULT_DIR%" installer.iss

if errorlevel 1 (
  echo [ERROR] Installer build failed.
  exit /b 1
)

echo.
echo ========================================
echo SUCCESS: dist\YVmonitor-Setup.exe
echo ========================================
pause
exit /b 0
