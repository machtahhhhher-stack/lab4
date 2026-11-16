@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py
echo Устанавливаю библиотеки (нужен интернет, первый раз 1-2 минуты)...
%PY% -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo Не удалось установить библиотеки. Проверьте интернет.
  pause
  exit /b 1
)
echo.
echo Бот запускается. Пока это окно открыто - бот работает.
echo Чтобы остановить бота, закройте окно или нажмите Ctrl+C.
echo.
%PY% bot.py
pause
