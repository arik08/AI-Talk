@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist apps\web\node_modules (
  echo 처음 실행입니다. install.bat을 먼저 실행해 주세요.
  pause
  exit /b 1
)
echo 화면을 빌드합니다.
pushd apps\web
call npm run build >nul || (popd & echo 화면 빌드에 실패했습니다. & pause & exit /b 1)
popd
pushd apps\server
python -m aitalk --open
popd
