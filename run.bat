@echo off
chcp 65001 >nul
title ChannelScraper 2.0
cd /d "%~dp0"

echo ==========================================================
echo    ChannelScraper 2.0
echo    Starting dashboard and opening browser...
echo ==========================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [ERROR] Python is not installed or not in PATH!
  echo   Please install Python from https://www.python.org/downloads/
  echo   and make sure to tick "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

python core\app.py
if errorlevel 1 (
  echo.
  echo   [STOPPED] Application stopped. See details above.
  echo.
  pause
)
