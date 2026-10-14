@echo off
rem Tränar om PanelViews rutmodell på grafikkortet (CoMix + dina rättade sidor) och installerar den om den blir bättre.
rem Tar ca 1-1,5 timme på RTX 3090. Stäng spel och LoRA-träning först.
title PanelView modellträning
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
".venv-export\Scripts\python.exe" build_tools\train_model.py %*
echo.
echo Historik: %LOCALAPPDATA%\PanelView\training\historik.jsonl
pause
