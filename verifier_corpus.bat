@echo off
rem Verification du corpus de grilles sur les vraies seances de louange.
rem 1) importe le corpus Chordonomicon (telecharge une fois, ~264 Mo, puis ~3 min)
rem 2) reetudie les seances ecoutees et compare : regles generiques / corpus + habitudes de lequipe
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" -m orchestre_ia --learn-corpus
if errorlevel 1 goto fin
".venv\Scripts\python.exe" -m orchestre_ia --learn-study --force
:fin
echo.
pause
