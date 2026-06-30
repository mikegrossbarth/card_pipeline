@echo off
setlocal
cd /d "%~dp0"

set "LUCAS_SETTINGS_PATH=%~dp0lucas_settings.json"
set "LUCAS_ASSIGNMENT_CONFIG_PATH=%~dp0assignment_companies.json"

call "Run Card Pipeline.bat"
