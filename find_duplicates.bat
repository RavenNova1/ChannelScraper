@echo off
chcp 65001 >nul
title ChannelScraper - Find Duplicates
cd /d "%~dp0"

echo ==========================================================
echo    ChannelScraper - Duplicate & Re-upload Finder
echo ==========================================================
echo.

python core\find_duplicates.py %*
echo.
pause
