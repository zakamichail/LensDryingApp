#!/bin/bash
set -e

cd "$(dirname "$0")"
APP_PORT="${PORT:-5055}"

if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
else
    echo 'Python не найден. Установите Python 3.11 или новее и повторите запуск.'
    exit 1
fi

if [ ! -f ".venv/bin/python" ]; then
    echo 'Создание виртуального окружения...'
    "$PY_CMD" -m venv .venv
fi

".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -r requirements.txt

if [ -d "data/postgres" ]; then
    if command -v pg_isready >/dev/null 2>&1 && command -v pg_ctl >/dev/null 2>&1; then
        if ! pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
            echo 'Запуск локального PostgreSQL...'
            pg_ctl -D data/postgres -l data/postgres.log -o "-k /tmp -p 5432" -w start
        fi
        export DATABASE_URL="postgresql+psycopg://lens_user:lens_password@localhost:5432/lens_drying"
        echo 'База данных: PostgreSQL'
    else
        echo 'PostgreSQL не найден в PATH. Приложение будет запущено с SQLite.'
    fi
fi

echo
echo 'Приложение будет доступно по адресу:'
printf 'http://127.0.0.1:%s\n' "$APP_PORT"
echo
echo 'Для остановки нажмите Ctrl+C в этом окне.'
echo

(sleep 2; xdg-open "http://127.0.0.1:$APP_PORT") >/dev/null 2>&1 &
".venv/bin/python" run.py
