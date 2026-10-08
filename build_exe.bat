@echo off
title Build Stealth Assistant Executable
color 0a
echo =======================================================================
echo    COMPILING STEALTH ASSISTANT (100%% SILENT BACKGROUND EXE)
echo =======================================================================
echo.
echo [1/3] Verifying and installing required packages...
pip install --upgrade pyinstaller pynput pyperclip requests Pillow pytesseract

echo.
echo [2/3] Building executable with PyInstaller in Windows GUI mode...
echo Flags: --noconsole (No terminal) --onefile (Single portable exe)
echo.
pyinstaller --noconsole --windowed --onefile --clean --name "SystemMonitor" win_assistant.py

echo.
echo [3/3] Build finished!
echo =======================================================================
echo    SUCCESS! Your stealth executable is ready:
echo    LOCATION: dist\SystemMonitor.exe
echo.
echo    When you run dist\SystemMonitor.exe:
echo    - Runs 100%% SILENTLY in the background
echo    - ZERO terminal / command prompt windows
echo    - ZERO icons in the Windows Taskbar
echo    - Press Right Shift + Y / H to toggle Typing Mode (Auto vs Interactive Hacker Typer)
echo    - Press Right Shift + P to start/pause typing | Esc to emergency stop
echo =======================================================================
echo.
pause
