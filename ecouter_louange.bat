@echo off
rem Ecoute muette de la louange pour l'apprentissage d'ORCHESTRE IA.
rem Double-cliquer pour demarrer, Ctrl+C pour arreter. Aucun son n'est joue.
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" -m orchestre_ia --learn-listen --label louange %*
echo.
pause
