@echo off
cd /d "%~dp0"
echo ========================================
echo  MIRANCE - Debug Mode
echo ========================================
echo.

:: Find Python (try embedded first, then system Python)
set "PYTHON="
if exist "python\python.exe" (
    set "PYTHON=python\python.exe"
) else (
    set "PYTHON=python"
)

:: Generate timestamped log filename
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "logfile=mirance_debug_%dt:~0,8%_%dt:~8,6%.log"

echo Using: %PYTHON%
echo Logging to: %logfile%
echo.

%PYTHON% -m mirance.main --verbose --log-file "%logfile%" 2>&1

echo.
echo ========================================
echo  App exited. Log saved to: %logfile%
echo ========================================
echo Press any key to close...
pause >nul
