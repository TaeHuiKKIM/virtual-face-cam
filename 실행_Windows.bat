@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Virtual Face Cam

echo Virtual Face Cam 준비 중...

REM Python 확인
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 설치 후 다시 실행하세요.
    echo 설치 시 "Add Python to PATH" 체크를 꼭 켜세요.
    echo.
    pause
    exit /b
)

python -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 (
    echo.
    echo [오류] Python 3.10 이상이 필요합니다.
    echo https://www.python.org/downloads/ 에서 최신 Python을 설치하세요.
    echo.
    pause
    exit /b
)

REM 의존성 설치 여부 확인
python -c "import pyvirtualcam, numpy, PIL" >nul 2>nul
if errorlevel 1 (
    echo 필요한 패키지를 설치합니다. 잠시만 기다려 주세요...
    python -m pip install -r requirements.txt
)

python gui.py
if errorlevel 1 pause
