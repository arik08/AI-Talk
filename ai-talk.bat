@echo off
chcp 65001 >nul
title AI-Talk
cd /d "%~dp0"
if not exist .env (
  echo .env 파일이 없습니다. installer.bat을 먼저 실행해 주세요.
  pause
  exit /b 1
)
rem 실행기가 서버를 따로 켜고 이 창의 키를 읽는다: R = 하드 리셋, Ctrl+C = 끝내기
python scripts\launch_aitalk.py
set CODE=%ERRORLEVEL%
if not %CODE%==0 pause
exit /b %CODE%
