@echo off
echo Starting build...
python -m PyInstaller --noconsole --windowed --onefile --clean win_assistant.py
if %ERRORLEVEL% EQU 0 (
    echo PyInstaller succeeded!
    echo Standalone executable created at dist\win_assistant.exe
) else (
    echo PyInstaller failed with error %ERRORLEVEL%.
)
