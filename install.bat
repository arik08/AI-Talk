@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] 파이썬 패키지를 설치합니다.
python -m pip install -r apps\server\requirements.txt || goto :fail
echo [2/2] 화면 패키지를 설치하고 빌드합니다.
pushd apps\web
call npm install || (popd & goto :fail)
call npm run build || (popd & goto :fail)
popd
if not exist .env copy .env.example .env >nul
echo.
echo 설치가 끝났습니다. .env를 열어 AITALK_PROVIDER와 키를 채운 뒤 run.bat을 실행하세요.
pause
exit /b 0
:fail
echo.
echo 설치하지 못했습니다. 위의 오류를 확인해 주세요.
pause
exit /b 1
