@echo off
rem Retrains the AutoComix panel model on the graphics card (CoMix + your corrected pages) and installs it if it gets better.
rem Takes about 1-1.5 hours on an RTX 3090 (needs an NVIDIA card). Close games and other GPU work first.
title AutoComix model training
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
".venv-export\Scripts\python.exe" build_tools\train_model.py %*
echo.
echo Historik: %LOCALAPPDATA%\AutoComix\training\historik.jsonl
pause
