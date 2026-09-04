@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion

title Audion Address Processor - Cleanup

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"
cd /d "%BASE_DIR%" || exit /b 1

set "AUTO_YES=0"
set "NO_PAUSE=0"
for %%A in (%*) do (
  if /I "%%~A"=="/Y" set "AUTO_YES=1"
  if /I "%%~A"=="/YES" set "AUTO_YES=1"
  if /I "%%~A"=="--yes" set "AUTO_YES=1"
  if /I "%%~A"=="/NOPAUSE" set "NO_PAUSE=1"
  if /I "%%~A"=="--no-pause" set "NO_PAUSE=1"
)

if not exist "%BASE_DIR%\system_core\" goto BAD_ROOT
if not exist "%BASE_DIR%\config\" goto BAD_ROOT
if not exist "%BASE_DIR%\install\init_folders.cmd" goto BAD_ROOT

echo ======================================================================
echo   AUDION ADDRESS ALIGNER - CLEANUP
echo ======================================================================
echo Root: %BASE_DIR%
echo.
echo This returns the project folder to a source-like state.
echo Code, launchers, configs, docs and folder skeletons are kept.
echo.
echo Managed contents to remove:
echo   input\*
echo   output\*
echo   logs\*
echo   report\*
echo   workspace\*
echo   release\*
echo   runtime\*
echo   wheelhouse\*
echo   ._runtime\*
echo   install\download\*
echo   system_core\powershell\*
echo   system_core\_pwsh_tmp\
echo   system_core\_powershell_tmp\
echo   system_core\_fzf_tmp\
echo   system_core\fzf.exe
echo.
echo Kept project data:
echo   data\*  (OKTMO registry and local project data)
echo.
echo Also removed recursively:
echo   __pycache__\
echo   *.pyc
echo   *.pyo
echo.

if "%AUTO_YES%"=="1" goto CLEAN_START
choice /C YNQ /N /M "Proceed with project cleanup? [Y/N/Q]: "
if errorlevel 2 (
  echo.
  echo [CANCELLED] Nothing was deleted.
  call :WAIT_IF_NEEDED
  exit /b 0
)

:CLEAN_START
call "%BASE_DIR%\install\init_folders.cmd" >nul 2>nul

call :CLEAN_DIR "%BASE_DIR%\input"
call :CLEAN_DIR "%BASE_DIR%\output"
call :CLEAN_DIR "%BASE_DIR%\logs"
call :CLEAN_DIR "%BASE_DIR%\report"
call :CLEAN_DIR "%BASE_DIR%\workspace"
call :CLEAN_DIR "%BASE_DIR%\release"
call :CLEAN_DIR "%BASE_DIR%\runtime"
call :CLEAN_DIR "%BASE_DIR%\wheelhouse"
call :CLEAN_DIR "%BASE_DIR%\._runtime"
call :CLEAN_DIR "%BASE_DIR%\install\download"
call :CLEAN_DIR "%BASE_DIR%\system_core\powershell"
call :DELETE_DIR "%BASE_DIR%\system_core\_pwsh_tmp"
call :DELETE_DIR "%BASE_DIR%\system_core\_powershell_tmp"
call :DELETE_DIR "%BASE_DIR%\system_core\_fzf_tmp"
call :DELETE_FILE "%BASE_DIR%\system_core\fzf.exe"

call :CLEAN_PYTHON_CACHE "%BASE_DIR%"

call "%BASE_DIR%\install\init_folders.cmd" >nul 2>nul

echo.
echo [OK] Cleanup finished. Only source files, folders, docs and configs should remain.
call :WAIT_IF_NEEDED
exit /b 0

:BAD_ROOT
echo [ERROR] This script must be launched from the project root.
echo Expected folders:
echo   system_core\
echo   config\
echo   install\
call :WAIT_IF_NEEDED
exit /b 1

:CLEAN_DIR
set "TARGET=%~1"
if "%TARGET%"=="" goto :eof
if /I "%TARGET%"=="%BASE_DIR%" goto :eof
if not exist "%TARGET%\" goto :eof
echo Cleaning: %TARGET%
for /f "delims=" %%F in ('dir /b /a "%TARGET%" 2^>nul') do (
    if exist "%TARGET%\%%F\" (
      rd /s /q "%TARGET%\%%F" >nul 2>nul
    ) else (
      del /f /q /a "%TARGET%\%%F" >nul 2>nul
    )
)
goto :eof

:DELETE_DIR
set "TARGET_DIR=%~1"
if "%TARGET_DIR%"=="" goto :eof
if /I "%TARGET_DIR%"=="%BASE_DIR%" goto :eof
if exist "%TARGET_DIR%\" (
  echo Deleting: %TARGET_DIR%
  attrib -r -s -h "%TARGET_DIR%\*" /s /d >nul 2>nul
  rd /s /q "%TARGET_DIR%" >nul 2>nul
)
goto :eof

:DELETE_FILE
set "TARGET_FILE=%~1"
if "%TARGET_FILE%"=="" goto :eof
if exist "%TARGET_FILE%" (
  echo Deleting: %TARGET_FILE%
  del /f /q /a "%TARGET_FILE%" >nul 2>nul
)
goto :eof

:CLEAN_PYTHON_CACHE
set "CACHE_ROOT=%~1"
if "%CACHE_ROOT%"=="" goto :eof
echo Cleaning Python caches...
for /d /r "%CACHE_ROOT%" %%D in (__pycache__) do (
  if exist "%%D\" rd /s /q "%%D" >nul 2>nul
)
for /r "%CACHE_ROOT%" %%F in (*.pyc *.pyo) do (
  if exist "%%F" del /f /q /a "%%F" >nul 2>nul
)
goto :eof

:WAIT_IF_NEEDED
if "%AUTO_YES%"=="1" goto :eof
if "%NO_PAUSE%"=="1" goto :eof
call :WAIT_KEY
goto :eof

:WAIT_KEY
echo Press any key to continue . . .
if not defined AUDION_NO_PAUSE pause >nul
goto :eof
