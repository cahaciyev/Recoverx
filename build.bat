@echo off
REM ============================================================
REM  Recoverix - one-click build of the standalone .exe
REM  Produces dist\Recoverix.exe  (runs with NO Python needed)
REM ============================================================
setlocal

echo.
echo [1/2] Installing build dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: dependency install failed. Is Python installed and on PATH?
    pause
    exit /b 1
)

echo.
echo [2/2] Building Recoverix.exe ...
python build.py
if errorlevel 1 (
    echo.
    echo ERROR: build failed. See messages above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  DONE.  Your standalone app:  dist\Recoverix.exe
echo  Copy that single file to any Windows PC - no Python needed.
echo ============================================================
echo.
pause
endlocal
