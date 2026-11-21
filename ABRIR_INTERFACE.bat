@echo off
rem Abre a interface web local do Rota no navegador.
cd /d "%~dp0"
if not exist ".venv\Scripts\rota.exe" (
  echo Rode primeiro o RODAR_ROTA.bat
  pause
  exit /b 1
)
".venv\Scripts\rota.exe" ui
