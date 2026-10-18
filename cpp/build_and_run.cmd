@echo off
rem Build and run the cloud-math verification with MSVC (x64).
rem Usage: cmd /c cpp\build_and_run.cmd
setlocal
call "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 >nul 2>&1
if errorlevel 1 (
    echo VsDevCmd failed
    exit /b 1
)
cd /d "%~dp0.."
cl /nologo /EHsc /O2 /fp:precise cpp\cloud_math.cpp /Fe:cpp\cloud_math.exe
if errorlevel 1 (
    echo build failed
    exit /b 1
)
cpp\cloud_math.exe
exit /b %errorlevel%
