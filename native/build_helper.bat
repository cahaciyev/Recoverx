@echo off
REM ============================================================
REM  Compile the native SMART helper (smarthelper.exe).
REM  Requires Visual Studio Build Tools (MSVC). Run from anywhere.
REM  Output -> recoverix\resources\smarthelper.exe (bundled into the app)
REM ============================================================
setlocal
set ROOT=%~dp0..

REM Locate MSVC via vswhere and set up the x64 dev environment.
set VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe
if not exist "%VSWHERE%" (
    echo ERROR: Visual Studio not found. Install "Build Tools for Visual Studio".
    exit /b 1
)
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -find VC\Auxiliary\Build\vcvars64.bat`) do set VCVARS=%%i
if not defined VCVARS (
    echo ERROR: vcvars64.bat not found ^(install the C++ workload^).
    exit /b 1
)

call "%VCVARS%"
cl /EHsc /O2 /nologo /Fo"%ROOT%\native\\" "%ROOT%\native\smarthelper.cpp" ^
   /Fe:"%ROOT%\recoverix\resources\smarthelper.exe" user32.lib
if errorlevel 1 ( echo BUILD FAILED & exit /b 1 )

echo.
echo Done -> recoverix\resources\smarthelper.exe
endlocal
