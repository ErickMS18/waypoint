@echo off
rem Roda o Waypoint inteiro (instala na primeira vez). Log em data\logs\ultima_execucao.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\rodar.ps1"
