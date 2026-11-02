@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title ChannelScraper - Smart Incremental Updater
echo ===================================================
echo     ChannelScraper - Smart Incremental Updater
echo ===================================================
echo.
python core\update_channel.py %*
echo.
pause
