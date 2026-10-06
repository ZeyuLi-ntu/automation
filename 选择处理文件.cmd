@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "scripts\configure_workbooks.ps1"
if errorlevel 1 pause
