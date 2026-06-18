@echo off

cd /d F:\strava

echo =====================
echo RUN COLLECTOR
echo =====================

F:\Python312\python.exe collector_fixed.py

echo.

echo =====================
echo RUN UPLOAD SHEET
echo =====================

F:\Python312\python.exe upload_sheet_fixed.py

echo.

echo =====================
echo DONE
echo =====================

pause