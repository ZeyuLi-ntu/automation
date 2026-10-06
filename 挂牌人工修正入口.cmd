@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 -m scripts.review_server --dataset board --port 8766
pause
