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
".venv\Scripts\python.exe" -c "import tkinter" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Python installed, but Tkinter is not available.
    echo.
    echo Reinstall Python from python.org and include Tcl/Tk support.
    echo Then run this installer again.
    echo.
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
)

echo.
echo Dependencies installed.
echo Open .env and add GOOGLE_API_KEY if you use Photo OCR or OCR fallback.
pause
