@echo off
chcp 65001 >nul
title PikPak 云端 AV 极速一键整理 (Pro版)
color 0A

echo ========================================================
echo       PikPak 云端 AV 目录批量整理与广告清理
echo ========================================================
echo.

set "PY_EXE=C:\Users\HiWin11\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
if not exist "%PY_EXE%" (
    set "PY_EXE=python"
)

"%PY_EXE%" "%~dp0pikpak_organizer_pro.py"

echo.
pause
