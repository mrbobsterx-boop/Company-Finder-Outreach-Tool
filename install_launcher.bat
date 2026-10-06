@echo off
REM One-time setup: adds a "Company Finder and Outreach" shortcut to the
REM Desktop that runs run_gui.bat, so the tool can be launched with a
REM double-click instead of typing commands in a terminal.
cd /d "%~dp0"
set "PROJECT_DIR=%cd%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%USERPROFILE%\Desktop\Company Finder and Outreach.lnk'); $s.TargetPath = '%PROJECT_DIR%\run_gui.bat'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.IconLocation = 'shell32.dll,14'; $s.Save()"

if errorlevel 1 (
    echo Could not create the shortcut. Try running this file again, or ask for help.
) else (
    echo Done! A "Company Finder and Outreach" shortcut was added to your Desktop.
)
pause
