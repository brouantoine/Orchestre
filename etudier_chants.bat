@echo off
rem Etudie un dossier de chants pour l'apprentissage d'ORCHESTRE IA.
rem Glisser-deposer un dossier sur ce fichier, ou double-cliquer pour etudier
rem le dossier Musique\Orchestre chants. Ctrl+C pour interrompre (reprise possible).
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" -m orchestre_ia --learn-library %*
echo.
pause
