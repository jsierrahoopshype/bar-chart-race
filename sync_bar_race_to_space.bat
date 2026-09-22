@echo off
REM One-click sync: push hf_space/ changes to the HuggingFace Space.
REM Double-click this file. The window stays open so you can read the result.
cd /d "%~dp0"
python scripts\sync_bar_race_to_space.py %*
pause
