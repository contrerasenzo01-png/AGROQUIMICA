@echo off
REM Job diario de alertas (Parcial 2 - M3).
REM Programarlo con:
REM   schtasks /create /sc daily /st 08:00 /tn "Agroquimica - alertas" /tr "D:\AGROQUIMICA\revisar_alertas.bat"
cd /d "%~dp0"
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe manage.py revisar_alertas >> revisar_alertas.log 2>&1
) else (
    python manage.py revisar_alertas >> revisar_alertas.log 2>&1
)
