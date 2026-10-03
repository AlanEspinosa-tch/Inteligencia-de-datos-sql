@echo off
REM Arranca la API. Doble clic, o desde cmd en esta carpeta.
setlocal
set PYTHONDONTWRITEBYTECODE=1
cd /d "%~dp0"

if not exist "%USERPROFILE%\.venvs\treher\Scripts\python.exe" (
    echo No encuentro el entorno virtual. Creandolo...
    python -m venv "%USERPROFILE%\.venvs\treher" || goto :error
    "%USERPROFILE%\.venvs\treher\Scripts\python.exe" -m pip install --upgrade pip
    "%USERPROFILE%\.venvs\treher\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)

REM .env es opcional: sin el, red.db se busca junto a esta carpeta.
if not exist ".env" copy /y ".env.example" ".env" >nul

if not exist "..\red.db" (
    echo.
    echo No encuentro red.db junto a la carpeta app.
    echo Abre la carpeta 01.Competencia en el Explorador y confirma que
    echo red.db este descargado, sin el icono de nube de SharePoint.
    goto :error
)

REM El mapa vive en la raiz. La documentacion de la API esta en /docs.
echo.
echo   Mapa : http://127.0.0.1:8000/
echo   API  : http://127.0.0.1:8000/docs
echo.
echo Para detener el servidor: Ctrl+C en esta ventana.
echo.
start "" http://127.0.0.1:8000/
REM Sin --reload a proposito: vigilaba esta carpeta, que esta en SharePoint,
REM y cada sincronizacion reiniciaba el servidor. Si cambias codigo, cierra
REM la ventana con Ctrl+C y vuelve a correr este archivo.
"%USERPROFILE%\.venvs\treher\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
goto :eof

:error
echo.
echo Algo fallo. Revisa el mensaje de arriba.
pause
