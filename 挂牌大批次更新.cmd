@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 -m scripts.run_board_bulk %*
pause
