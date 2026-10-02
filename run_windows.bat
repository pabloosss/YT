@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Tworze srodowisko Python...
    py -m venv .venv
    if errorlevel 1 (
        echo Nie mozna utworzyc srodowiska. Zainstaluj Python 3.11 lub nowszy.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

echo Sprawdzam zaleznosci...
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo Nie udalo sie zainstalowac zaleznosci.
    pause
    exit /b 1
)

python app.py
if errorlevel 1 pause

