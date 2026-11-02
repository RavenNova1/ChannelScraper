@echo off
chcp 65001 >nul
title Continue ChannelScraper
cd /d "%~dp0"

echo ==========================================================
echo    Continuing ChannelScraper without restarting...
echo ==========================================================
echo.

python core\continue_run.py %*
echo.
pause
