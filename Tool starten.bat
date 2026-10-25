@echo off
REM Doppelklick zum Starten (Windows). Das Tool oeffnet sich im Browser.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Die Python-Umgebung fehlt. Bitte zuerst die Installation aus der README durchfuehren.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py
