@echo off
rem Election night 2026: poll civicAPI for results and publish them to the site's live page.
rem Run by the Windows scheduled task "Politics - election night results" (Nov 3, 2026, 5:45 PM ET; wakes the PC).
rem The poller keeps the PC awake while it runs and stops at 4 AM ET on Nov 4 (or once every race is called).
rem Output goes to logs\election_night_run.log (not committed); the poller's own log is logs\election_night_YYYY-MM-DD.log.
cd /d "%~dp0.."
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
".venv\Scripts\python.exe" scripts\election_night.py >> "logs\election_night_run.log" 2>&1
