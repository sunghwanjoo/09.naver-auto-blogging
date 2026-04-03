@echo off
chcp 65001 >nul
echo.
echo ========================================
echo   Naver Blog Tool - EXE Build
echo ========================================
echo.

echo [1/3] Installing packages...
pip install -r requirements.txt >nul 2>&1
pip install pyinstaller >nul 2>&1
echo     Done.

echo [2/3] Stopping running processes...
taskkill /IM NaverBlogTool.exe /F >nul 2>&1
taskkill /IM NaverBlogTool.exe /T /F >nul 2>&1
timeout /t 1 /nobreak >nul
echo     Done.

echo [2/3] Cleaning previous build...
if exist dist\NaverBlogTool rmdir /s /q dist\NaverBlogTool
if exist build rmdir /s /q build
if exist dist\NaverBlogTool (
  echo [FAIL] Could not delete dist folder. Process may still be running.
  pause
  exit /b 1
)
echo     Done.

echo [3/3] Building EXE (1~3 min)...
pyinstaller NaverBlogTool.spec --noconfirm --clean

echo.
if not exist dist\NaverBlogTool\NaverBlogTool.exe (
  echo ========================================
  echo   Build FAILED. Check error above.
  echo ========================================
  pause
  exit /b 1
)

echo [+] Verifying certifi bundle...
if not exist "dist\NaverBlogTool\_internal\certifi\cacert.pem" (
  echo ========================================
  echo   [FAIL] certifi/cacert.pem missing! Do NOT distribute this build.
  echo ========================================
  pause
  exit /b 1
)

echo [+] Copying config.json to dist...
if exist config.json copy /Y config.json dist\NaverBlogTool\config.json >nul
echo ========================================
echo   Build SUCCESS! Launching...
echo ========================================
start "" "dist\NaverBlogTool\NaverBlogTool.exe"
