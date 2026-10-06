@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\run_market.ps1" -Mode rebuild
if errorlevel 1 echo Failed. Evidence and logs have been saved. See the message above.
pause
