@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app.py
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        py -3 app.py
    ) else (
        where python >nul 2>nul
        if %ERRORLEVEL% EQU 0 (
            python app.py
        ) else (
            echo L.U.C.A.S could not find Python.
            echo.
            echo Run install_dependencies.bat after installing Python 3.11 or newer from python.org.
            echo Make sure "Add python.exe to PATH" is checked during install.
            echo.
            pause
        )
    )
)
