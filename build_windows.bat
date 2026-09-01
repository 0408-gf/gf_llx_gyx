@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
py -3.11 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 exit /b 1
python -m pytest
if errorlevel 1 exit /b 1
python -m scripts.smoke_test
if errorlevel 1 exit /b 1
pyinstaller football_jc_onefile.spec --clean --noconfirm
if errorlevel 1 exit /b 1
if not exist "dist\FootballJCAssistant.exe" (
  echo ERROR: dist\FootballJCAssistant.exe was not created.
  exit /b 1
)
echo Build complete: dist\FootballJCAssistant.exe
pause
