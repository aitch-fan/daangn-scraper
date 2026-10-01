@echo off
chcp 65001 >nul
title 당근마켓 아이폰 정보 추출기

echo ============================================================
echo   당근마켓 아이폰 정보 추출기 - 자동 실행기
echo ============================================================
echo.

:: 1. 파이썬 설치 여부 확인
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [오류] 컴퓨터에 Python이 설치되어 있지 않습니다!
    echo 마이크로소프트 스토어 또는 아래 사이트에서 Python을 먼저 설치해주세요:
    echo https://www.python.org/downloads/
    echo (설치 시 반드시 'Add Python to PATH' 옵션을 체크해주세요)
    echo.
    pause
    exit /b
)

:: 2. 가상환경(.venv) 확인 및 생성
if not exist ".venv" (
    echo [안내] 최초 실행: 가상환경(.venv)을 생성하는 중입니다. 잠시만 기다려주세요...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [오류] 가상환경 생성에 실패했습니다.
        pause
        exit /b
    )
    echo [완료] 가상환경이 성공적으로 생성되었습니다.
    echo.
)

:: 3. 필수 패키지 설치 (requirements.txt)
echo [안내] 필수 라이브러리를 점검하고 있습니다...
call .\.venv\Scripts\pip.exe install -r requirements.txt >nul 2>nul
if %errorlevel% neq 0 (
    echo [안내] 라이브러리 설치를 재시도합니다...
    call .\.venv\Scripts\pip.exe install -r requirements.txt
)

:: 4. Playwright 브라우저(크로미움) 점검 및 설치
call .\.venv\Scripts\playwright.exe install chromium >nul 2>nul
if %errorlevel% neq 0 (
    echo [안내] 크롤링용 브라우저 설치 중...
    call .\.venv\Scripts\playwright.exe install chromium
)

echo.
echo ============================================================
echo   모든 준비가 완료되었습니다! 프로그램을 시작합니다.
echo ============================================================
echo.

:: 5. 프로그램 실행
call .\.venv\Scripts\python.exe daangn_scraper.py

:: 6. 종료 시 창 유지
echo.
pause
