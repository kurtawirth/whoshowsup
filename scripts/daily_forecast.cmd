@echo off
rem Daily 2026 forecast: refresh all data, rerun the models, push results to GitHub.
rem Run by the Windows scheduled task "Politics - daily midterm forecast" (7:00 AM; wakes the PC).
rem Each day's output goes to logs\forecast_YYYY-MM-DD.log (not committed).
rem Afterwards, scripts\sleep_if_idle.ps1 puts the PC back to sleep if the task woke it and nobody is using it.
cd /d "%~dp0.."
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
for /f %%s in ('powershell -NoProfile -Command "Get-Date -Format s"') do set TASKSTART=%%s
".venv\Scripts\python.exe" midterms_2026\run_forecast.py --push >> "logs\forecast_%TODAY%.log" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\sleep_if_idle.ps1" -TaskStart "%TASKSTART%" >> "logs\forecast_%TODAY%.log" 2>&1
