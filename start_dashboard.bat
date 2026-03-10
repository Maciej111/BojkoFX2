@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: start_dashboard.bat — uruchamia lokalny dashboard BojkoFX2
::
:: Otwiera http://localhost:8890 i proxy'uje /api/* do VM (34.31.64.224:8080)
::
:: Zmienne środowiskowe (opcjonalne):
::   VM_API=http://34.31.64.224:8080   adres VM z botem
::   API_KEY=twoj-klucz                klucz z ibkr.env na serwerze
::   DASHBOARD_LOCAL_PORT=8890         lokalny port
:: ─────────────────────────────────────────────────────────────────────────────

:: Domyślny klucz i adres VM — zmień jeśli potrzeba
if "%VM_API%"==""  set VM_API=http://34.31.64.224:8080
if "%API_KEY%"=="" set API_KEY=changeme

echo.
echo  BojkoFX2 Dashboard
echo  ══════════════════════════════════════════
echo  Lokalny port : http://localhost:8890
echo  VM API       : %VM_API%
echo  Press Ctrl+C to stop.
echo  ══════════════════════════════════════════
echo.

:: Otwiera przeglądarkę po 2 sekundach (w tle)
start "" cmd /c "timeout /t 2 >nul && start http://localhost:8890"

:: Uruchamia serwer
python dashboard\serve.py
