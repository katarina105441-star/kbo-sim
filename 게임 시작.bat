@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ================================================
echo  KBO 매니저 실행 준비
echo ================================================

where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [오류] Python 3를 찾을 수 없습니다.
    echo https://www.python.org/downloads/ 에서 설치하면서
    echo "Add python.exe to PATH"를 체크하세요.
    pause
    exit /b 1
  )
  set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 전용 실행 환경을 만드는 중...
  %PY% -m venv .venv
  if errorlevel 1 goto :failed
)

if not exist ".venv\.kbo-ready-0.5.0" (
  echo [2/3] 필수 구성요소를 설치하는 중... 최초 1회만 실행됩니다.
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :failed
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
  type nul > ".venv\.kbo-ready-0.5.0"
) else (
  echo [2/3] 설치 확인 완료
)

echo [3/3] 게임을 시작합니다. 브라우저가 자동으로 열립니다.
".venv\Scripts\python.exe" run_game.py
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo [실행 실패] 위 오류 내용을 확인하세요.
echo QUICKSTART.md의 문제 해결 항목도 참고할 수 있습니다.
pause
exit /b 1
