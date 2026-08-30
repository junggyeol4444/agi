@echo off
echo ============================================
echo   AGI - One-click Install (Windows)
echo   Installs Python, packages, and browser.
echo ============================================
echo.

REM === Install path for programs (edit if needed) ===
set INSTALL_DIR=%~dp0programs
echo Program install path: %INSTALL_DIR%
echo.

REM --- 1) Check Python, auto-install if missing ---
python --version >nul 2>&1
if not errorlevel 1 goto PYOK

echo [1/4] Python not found. Trying auto-install...
winget --version >nul 2>&1
if not errorlevel 1 (
  echo     Installing Python via winget... please wait.
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
) else (
  echo.
  echo [!] winget not found. Cannot auto-install Python.
  echo     Please install Python from:  https://www.python.org/downloads/
  echo     IMPORTANT: check "Add Python to PATH" during install.
  echo     Then run this file again.
  pause & exit /b
)

python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo [!] Python installed but PATH not updated yet.
  echo     Close this window and run the bat file ONE more time.
  pause & exit /b
)

:PYOK
echo [1/4] Python OK.
python --version

REM --- 2) pip ---
echo [2/4] Preparing pip...
python -m pip install --upgrade pip >nul 2>&1

REM --- 3) Packages ---
echo [3/4] Installing packages (Pillow numpy kollocate playwright pytesseract)...
python -m pip install Pillow numpy kollocate playwright pytesseract
if errorlevel 1 (
  echo [!] Package install failed. Check internet and run again.
  pause & exit /b
)

REM --- 4) Browser (chromium) into install path ---
echo [4/4] Installing browser (chromium)... this is large, please wait.
set PLAYWRIGHT_BROWSERS_PATH=%INSTALL_DIR%\browsers
mkdir "%PLAYWRIGHT_BROWSERS_PATH%" 2>nul
python -m playwright install chromium

echo.
echo [+] Optional: for "see like human" (OCR), install Tesseract:
echo     https://github.com/UB-Mannheim/tesseract/wiki  (include Korean)
echo     Then set SEE_LIKE_HUMAN = True in config.py
echo.
echo ============================================
echo   DONE!  Now run:    python server.py
echo   Then open browser:  http://localhost:8000
echo   (first start takes 1-2 min to load dictionaries)
echo ============================================
echo.
echo See the Korean guide file in this folder for details.
pause
