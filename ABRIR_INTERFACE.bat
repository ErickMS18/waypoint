@echo off
rem Abre a interface do Waypoint (sem precisar deixar o terminal aberto).
rem Dica: o RODAR_WAYPOINT.bat cria um atalho "Waypoint" na Area de Trabalho que faz o mesmo.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Rode primeiro o RODAR_WAYPOINT.bat
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "scripts\waypoint_launcher.pyw"
