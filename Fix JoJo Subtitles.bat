@echo off
rem Drag episode files or folders onto this file. Keep it next to fix_jojo_subtitles.py.
chcp 65001 >nul
python "%~dp0fix_jojo_subtitles.py" %*
