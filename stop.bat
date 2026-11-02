@echo off
title Stop ChannelScraper
echo ==========================================================
echo    Stopping ChannelScraper server...
echo ==========================================================

taskkill /F /IM yt-dlp.exe >nul 2>nul

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8760 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>nul
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8761 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>nul
)

echo.
echo Server stopped successfully.
echo.
timeout /t 3 >nul
