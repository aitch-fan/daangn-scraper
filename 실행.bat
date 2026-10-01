@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title 당근마켓 아이폰 정보 추출기

echo ============================================================
echo   당근마켓 아이폰 정보 추출기 - 자동 실행기
echo ============================================================
echo.

REM 1. 파이썬 설치 여부 확인
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [오류] 컴퓨터에 Python이 설치되어 있지 않거나 PATH에 등록되지 않았습니다.
    echo https://www.python.org/downloads/ 에서 Python을 설치해주세요.
    echo [설치 시 'Add Python to PATH' 옵션을 꼭 체크하세요!]
    echo.
    pause
    exit /b 1
)

REM 2. 가상환경 확인 및 생성
if not exist ".venv\Scripts\python.exe" (
    echo [안내] 가상환경 .venv 가 없어 새로 생성합니다. 잠시만 기다려주세요...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [오류] 가상환경 생성에 실패했습니다.
        pause
        exit /b 1
    )
    echo [완료] 가상환경이 생성되었습니다.
    echo.
)

REM 3. 필수 라이브러리 확인
echo [안내] 필수 라이브러리 상태를 점검하는 중입니다...
.\.venv\Scripts\python.exe -c "import httpx, playwright, google.genai, pydantic" >nul 2>nul
if %errorlevel% neq 0 (
    echo [안내] 필요한 라이브러리를 설치하고 있습니다. 잠시만 기다려주세요...
    call .\.venv\Scripts\pip.exe install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [오류] 라이브러리 설치 실패! 인터넷 연결을 확인해주세요.
        pause
        exit /b 1
    )
    echo [안내] 크롤링용 Chromium 브라우저를 설치하고 있습니다...
    call .\.venv\Scripts\playwright.exe install chromium
)

echo.
echo ============================================================
echo   모든 준비가 완료되었습니다! 스크래퍼를 실행합니다.
echo ============================================================
echo.

REM 4. 프로그램 실행
call .\.venv\Scripts\python.exe daangn_scraper.py

REM 5. 프로그램 종료 후 창 유지
echo.
echo ============================================================
echo   프로그램이 종료되었습니다.
echo ============================================================
pause
