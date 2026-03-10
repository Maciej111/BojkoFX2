@echo off
:: BojkoFx — Status Monitor (Windows wrapper)
:: Uruchamia status.sh przez Git Bash (nie przez WSL)
:: Uzycie: status.cmd  (lub dwuklik)

set GITBASH="C:\Program Files\Git\bin\bash.exe"
set SCRIPT=%~dp0status.sh

if not exist %GITBASH% (
    echo ERROR: Git Bash nie znaleziony w C:\Program Files\Git\bin\bash.exe
    echo Zainstaluj Git for Windows: https://git-scm.com/download/win
    pause
    exit /b 1
)

%GITBASH% -c "cd '%~dp0' && bash status.sh"

