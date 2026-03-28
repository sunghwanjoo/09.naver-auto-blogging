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
if exist NaverBlogTool.spec del NaverBlogTool.spec
echo     Done.

echo [3/3] Building EXE (1~3 min)...
for /f "delims=" %%i in ('python -c "import os,certifi; print(os.path.dirname(certifi.where()))"') do set CERTIFI_DIR=%%i
pyinstaller ^
  --noconfirm ^
  --onedir ^
  --name "NaverBlogTool" ^
  --add-data "templates;templates" ^
  --add-data "%CERTIFI_DIR%;certifi" ^
  --hidden-import=naver_bot ^
  --hidden-import=waitress ^
  --collect-all anthropic ^
  --collect-all certifi ^
  --collect-all selenium ^
  --collect-all webdriver_manager ^
  --noconsole ^
  app.py

echo.
if exist dist\NaverBlogTool\NaverBlogTool.exe (
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
