@echo off
REM Launches the local button-driven UI at http://localhost:8501
REM Safe to run every time: sets up the virtualenv on the very first run,
REM reuses it afterwards, and silences Streamlit's one-time onboarding
REM email prompt so it never blocks a double-click launch again.
cd /d "%~dp0"

if not exist ".venv" (
    echo First run - creating the virtual environment and installing dependencies, this can take a few minutes...
    python -m venv .venv
    if errorlevel 1 (
        echo Could not find "python". Install Python 3.11+ from python.org and make sure "Add python.exe to PATH" is checked during setup.
        pause
        exit /b 1
    )
    call ".venv\Scripts\activate.bat"
    python -m pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
)

if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    (echo [general]& echo email = "") > "%USERPROFILE%\.streamlit\credentials.toml"
)

set "URL=http://localhost:8501"
set "CHROME="

if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if defined CHROME (
    echo Opening in Chrome: %CHROME%
    start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process -FilePath '%CHROME%' -ArgumentList '--new-window','%URL%'"
    streamlit run gui\app.py --server.headless true
) else (
    echo Chrome not found - opening in the default browser instead.
    streamlit run gui\app.py
)
