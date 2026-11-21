@echo off
rem Abre a interface web local do Waypoint no navegador.
cd /d "%~dp0"
if not exist ".venv\Scripts\waypoint.exe" (
  echo Rode primeiro o RODAR_WAYPOINT.bat
  pause
  exit /b 1
)
".venv\Scripts\waypoint.exe" ui
