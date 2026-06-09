@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 -m venv .venv
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        python -m venv .venv
    ) else (
        echo L.U.C.A.S could not find Python.
        echo.
        echo Install Python 3.11 or newer from python.org.
        echo Make sure "Add python.exe to PATH" is checked during install.
        echo Then run this installer again.
        echo.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

if not exist ".env" (
    copy ".env.example" ".env" >nul
)

where npm >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    pushd cardladder-autocomp
    npm install
    popd
) else (
    echo npm was not found. Skipping optional Card Ladder CLI utility dependencies.
)

echo.
echo Dependencies installed.
echo Copy .env.example to .env and add GOOGLE_API_KEY if you use Photo OCR or OCR fallback.
pause
