@echo off
setlocal EnableExtensions

title Audion Address Processor - Remove Fully Empty Rows

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%\..") do set "BASE_DIR=%%~fI"
cd /d "%BASE_DIR%"

set "PYTHON_EXE=%BASE_DIR%\runtime\python.exe"
if not exist "%PYTHON_EXE%" (
  echo [ERROR] Python runtime not found:
  echo %PYTHON_EXE%
  if not defined AUDION_NO_PAUSE pause
  exit /b 1
)

if "%~1"=="" (
  echo Drag an .xlsx file onto this command file, or paste a file/folder path below.
  echo.
  set /p "TARGET=Excel file or folder: "
  if not defined TARGET exit /b 0
  "%PYTHON_EXE%" "%BASE_DIR%\system_core\remove_empty_rows.py" "%TARGET%"
) else (
  "%PYTHON_EXE%" "%BASE_DIR%\system_core\remove_empty_rows.py" %*
)

echo.
if not defined AUDION_NO_PAUSE pause
