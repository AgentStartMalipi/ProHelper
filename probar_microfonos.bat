@echo off
rem Prueba cada microfono con tu voz y dice cual usar en SPEAK.
rem Cierra SPEAK antes: si esta grabando, compite por el microfono.
setlocal
cd /d "%~dp0"
if not exist ".venv-speak\Scripts\python.exe" (
    echo Primero abre SPEAK una vez con run_speak.bat para preparar el entorno.
    pause
    exit /b 1
)
".venv-speak\Scripts\python.exe" -m speak --mics
echo.
pause
