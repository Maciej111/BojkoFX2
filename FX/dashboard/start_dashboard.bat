@echo off
echo Starting BojkoFx Dashboard...

REM Kill old instances
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":889[012] " 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak > nul

REM Start server on port 8892
start "bojkofx-dash" /B C:\Users\macie\anaconda3\python.exe C:\dev\projects\BojkoFx\dashboard\serve.py

timeout /t 3 /nobreak > nul

start "" "http://localhost:8892"
echo Done. Dashboard: http://localhost:8892

