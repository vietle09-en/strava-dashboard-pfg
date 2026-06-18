@echo off
cd /d F:\strava

echo ================================
echo BAT DAU DONG BO STRAVA
echo %date% %time%
echo ================================

F:\Python312\python.exe collector_oauth.py
F:\Python312\python.exe leaderboard_fixed.py
F:\Python312\python.exe upload_sheet_fixed.py

echo ================================
echo HOAN TAT
echo %date% %time%
echo ================================

pause