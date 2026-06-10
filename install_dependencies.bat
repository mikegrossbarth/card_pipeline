@echo off
setlocal
cd /d "%~dp0"

call :ensure_python
if %ERRORLEVEL% NEQ 0 (
    pause
    exit /b 1
)

%PYTHON_CMD% -m venv .venv
if %ERRORLEVEL% NEQ 0 (
    echo L.U.C.A.S could not create the Python virtual environment.
    echo.
    echo Try closing this window, opening a new Command Prompt, and running install_dependencies.bat again.
    echo If that still fails, install Python 3.11 or newer from python.org and include Tcl/Tk support.
    echo.
    pause
    exit /b 1
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
exit /b 0

:ensure_python
call :try_python py -3.13
if %ERRORLEVEL% EQU 0 exit /b 0
call :try_python py -3.12
if %ERRORLEVEL% EQU 0 exit /b 0
call :try_python py -3.11
if %ERRORLEVEL% EQU 0 exit /b 0
call :try_python py -3
if %ERRORLEVEL% EQU 0 exit /b 0
call :try_python python
if %ERRORLEVEL% EQU 0 exit /b 0

echo L.U.C.A.S could not find Python 3.11 or newer.
echo.
where winget >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Windows Package Manager ^(winget^) is not available on this computer.
    echo Install Python 3.11 or newer from python.org, include Tcl/Tk support,
    echo and check "Add python.exe to PATH". Then run this installer again.
    echo.
    exit /b 1
)

echo Attempting to install Python 3.11 with Windows Package Manager...
echo You may see a Windows installer or permission prompt.
echo.
winget install --id Python.Python.3.11 -e --source winget --accept-package-agreements --accept-source-agreements
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Automatic Python install failed.
    echo Install Python 3.11 or newer from python.org, include Tcl/Tk support,
    echo and check "Add python.exe to PATH". Then run this installer again.
    echo.
    exit /b 1
)

call :try_python py -3.11
if %ERRORLEVEL% EQU 0 exit /b 0
call :try_python "%LocalAppData%\Programs\Python\Python311\python.exe"
if %ERRORLEVEL% EQU 0 exit /b 0

echo.
echo Python was installed, but this command window cannot find it yet.
echo Close this window, open a new Command Prompt, and run install_dependencies.bat again.
echo.
exit /b 1

:try_python
%* -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=%*"
    exit /b 0
)
exit /b 1
