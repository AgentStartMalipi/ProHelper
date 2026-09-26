@echo off
rem Lanzador de SPEAK. La primera vez prepara su entorno (.venv-speak); despues solo abre.
rem SCREEN (el helper de capturas) sigue siendo run.bat.
setlocal
cd /d "%~dp0"

if not exist ".venv-speak\Scripts\pythonw.exe" (
    echo Preparando el entorno de SPEAK por primera vez, esto tarda unos minutos...
    py -m venv .venv-speak || goto :error
    ".venv-speak\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv-speak\Scripts\python.exe" -m pip install --quiet -r speak\requirements.txt || goto :error
    if not exist "speak\.env" copy "speak\.env.example" "speak\.env" >nul
    echo Listo.
)

rem "run_speak.bat notes" abre directo Notas de llamada.
if /i "%~1"=="notes" (
    start "" ".venv-speak\Scripts\pythonw.exe" -m speak --notes
) else (
    start "" ".venv-speak\Scripts\pythonw.exe" -m speak
)
exit /b 0

:error
echo.
echo No se pudo preparar el entorno de SPEAK.
echo Revisa que Python este instalado: abre una terminal y escribe  py --version
echo.
pause
exit /b 1
