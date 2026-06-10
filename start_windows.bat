@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"
if "%PORT%"=="" set PORT=5055

echo Запуск веб-приложения подбора режимов сушки линз

echo Проверка Python...
where py >nul 2>nul
if %errorlevel%==0 (
    set PY_CMD=py -3
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set PY_CMD=python
    ) else (
        echo Python не найден. Установите Python 3.11 или новее и повторите запуск.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Создание виртуального окружения...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo Не удалось создать виртуальное окружение.
        pause
        exit /b 1
    )
)

echo Установка зависимостей...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Не удалось установить зависимости.
    pause
    exit /b 1
)

if exist "data\postgres" (
    where pg_isready >nul 2>nul
    if not errorlevel 1 (
        where pg_ctl >nul 2>nul
        if not errorlevel 1 (
            pg_isready -h localhost -p 5432 >nul 2>nul
            if errorlevel 1 (
                echo Запуск локального PostgreSQL...
                pg_ctl -D "data\postgres" -l "data\postgres.log" -o "-p 5432" -w start
            )
            set DATABASE_URL=postgresql+psycopg://lens_user:lens_password@localhost:5432/lens_drying
            echo База данных: PostgreSQL
        ) else (
            echo PostgreSQL не найден в PATH. Приложение будет запущено с SQLite.
        )
    ) else (
        echo PostgreSQL не найден в PATH. Приложение будет запущено с SQLite.
    )
)

echo.
echo Приложение будет доступно по адресу:
echo http://127.0.0.1:%PORT%
echo.
echo Для остановки нажмите Ctrl+C в этом окне.
echo.
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:%PORT%'"
".venv\Scripts\python.exe" run.py

pause
