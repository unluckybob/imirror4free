@echo off
cd /d "%~dp0"
echo ========================================
echo  IMIRANCE - Debug Mode
echo ========================================
echo.

:: Generate timestamped log filename
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "logfile=imirror_debug_%dt:~0,8%_%dt:~8,6%.log"

echo Logging to: %logfile%
echo.

python\python.exe -m imirror.main --verbose --log-file "%logfile%" 2>&1 | findstr /v "^$"

echo.
echo ========================================
echo  App exited. Log saved to: %logfile%
echo ========================================
echo Press any key to close...
pause >nul
