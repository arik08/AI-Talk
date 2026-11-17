@echo off
chcp 65001 >nul
title AI-Talk
cd /d "%~dp0"
if not exist .env (
  echo .env 파일이 없습니다. installer.bat을 먼저 실행해 주세요.
  pause
  exit /b 1
)
pushd apps\server
python -m aitalk --open
set CODE=%ERRORLEVEL%
popd
if not %CODE%==0 pause
exit /b %CODE%
