@echo off
rem Daily 2026 forecast: refresh all data, rerun the models, push results to GitHub.
rem Run by the Windows scheduled task "Politics - daily midterm forecast".
rem Each day's output goes to logs\forecast_YYYY-MM-DD.log (not committed).
cd /d "%~dp0.."
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
".venv\Scripts\python.exe" midterms_2026\run_forecast.py --push >> "logs\forecast_%TODAY%.log" 2>&1
