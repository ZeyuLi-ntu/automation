@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\run_all.ps1" -Resume
if errorlevel 1 echo Failed. Progress and logs are saved.
pause
