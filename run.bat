@echo off
rem Lanzador del helper. La primera vez prepara el entorno; despues solo abre.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Preparando el entorno por primera vez, esto tarda un momento...
    py -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto :error
    echo Listo.
)

rem pythonw en vez de python: no deja una ventana de consola abierta detras.
start "" ".venv\Scripts\pythonw.exe" -m helper
exit /b 0

:error
echo.
echo No se pudo preparar el entorno.
echo Revisa que Python este instalado: abre una terminal y escribe  py --version
echo.
pause
exit /b 1
