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

echo [2/3] Cleaning previous build...
if exist dist\NaverBlogTool rmdir /s /q dist\NaverBlogTool
if exist build rmdir /s /q build
echo     Done.

echo [3/3] Building EXE (1~3 min)...
pyinstaller NaverBlogTool.spec --noconfirm

echo.
if exist dist\NaverBlogTool\NaverBlogTool.exe (
  echo [+] Copying config.json to dist...
  if exist config.json copy /Y config.json dist\NaverBlogTool\config.json >nul
  echo ========================================
  echo   Build SUCCESS! Launching...
  echo ========================================
  start "" "dist\NaverBlogTool\NaverBlogTool.exe"
) else (
  echo ========================================
  echo   Build FAILED. Check error above.
  echo ========================================
  pause
)
