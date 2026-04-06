@echo off
cd /d "%~dp0"
echo ========================================
echo  IMIRROR4FREE - Debug Mode
echo ========================================
echo.
python\python.exe -m imirror.main
echo.
echo ========================================
echo  App exited. Check output above for errors.
echo ========================================
echo Press any key to close...
pause >nul
