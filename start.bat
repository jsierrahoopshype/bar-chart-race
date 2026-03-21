@echo off
set PYTHONPATH=src
start "" python tools/server.py
timeout /t 2 /nobreak >nul
start http://localhost:8765
