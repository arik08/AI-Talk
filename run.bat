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
echo AI-Talk를 시작합니다. 브라우저에서 http://127.0.0.1:8765 가 열립니다. 끄려면 이 창에서 Ctrl+C를 누르세요.
start "" http://127.0.0.1:8765
python -m uvicorn --app-dir apps\server aitalk.app:app --host 127.0.0.1 --port 8765
