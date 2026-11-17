@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo AI-Talk 설치를 시작합니다.
echo.
where python >nul 2>nul || (echo Python을 찾지 못했습니다. Python 3.11 이상을 먼저 설치해 주세요. & pause & exit /b 1)
where npm >nul 2>nul || (echo Node.js를 찾지 못했습니다. Node.js를 먼저 설치해 주세요. & pause & exit /b 1)
echo [1/3] 파이썬 패키지를 설치합니다.
python -m pip install -r apps\server\requirements.txt || goto :fail
echo [2/3] 화면 패키지를 설치합니다.
pushd apps\web
call npm install || (popd & goto :fail)
echo [3/3] 화면을 빌드합니다.
call npm run build || (popd & goto :fail)
popd
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo .env 파일을 만들었습니다. 메모장이 열리면 AITALK_PROVIDER와 API 키를 채우고 저장해 주세요.
  start notepad .env
)
echo.
echo 설치가 끝났습니다. ai-talk.bat으로 실행합니다.
pause
exit /b 0
:fail
echo.
echo 설치하지 못했습니다. 위의 오류를 확인해 주세요.
pause
exit /b 1
