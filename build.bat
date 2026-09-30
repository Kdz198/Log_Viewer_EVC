@echo off
REM Build LogViewer.exe
REM   build.bat          -> dist\LogViewer\LogViewer.exe (mo nhanh)
REM   build.bat onefile  -> dist\LogViewer.exe (1 file, de gui cho nguoi khac)
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
"%PY%" -m pip install -q -r requirements.txt pyinstaller
set MODE=--onedir
if /i "%1"=="onefile" set MODE=--onefile
"%PY%" -m PyInstaller --noconfirm --clean --windowed %MODE% --name LogViewer main.py
echo.
echo Xong! Xem thu muc dist\
pause
