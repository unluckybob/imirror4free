@echo off
cd /d "%~dp0"
echo ========================================
echo  MIRANCE - Debug Mode
echo ========================================
echo.

:: Check for --diag flag
set "RUN_DIAG=0"
if "%1"=="--diag" set "RUN_DIAG=1"

:: Check if we're running from built EXE (ONE-DIR mode) or from source
if exist "MIRANCE.exe" (
    echo Running from EXE bundle...
    set "EXE_PATH=%CD%\MIRANCE.exe"
) else (
    echo Running from source...
    set "EXE_PATH="
)

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

:: Run with verbose + diagnostics
if "%RUN_DIAG%"=="1" (
    echo Running diagnostics...
    if not "%EXE_PATH%"=="" (
        "%EXE_PATH%" --diag --verbose --log-file "%logfile%" 2>&1
    ) else (
        %PYTHON% -m mirance --diag --verbose --log-file "%logfile%" 2>&1
    )
) else (
    if not "%EXE_PATH%"=="" (
        "%EXE_PATH%" --verbose --log-file "%logfile%" 2>&1
    ) else (
        %PYTHON% -m mirance --verbose --log-file "%logfile%" 2>&1
    )
)

echo.
echo ========================================
echo  App exited. Log saved to: %logfile%
echo ========================================
echo Press any key to close...
pause >nul
