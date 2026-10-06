@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 -m scripts.show_repair_report
if errorlevel 1 pause
