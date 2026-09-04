@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

title Audion Address Processor - Русский лаунчер

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"
cd /d "%BASE_DIR%"

set "CORE_DIR=%BASE_DIR%\system_core"
set "INSTALL_DIR=%BASE_DIR%\install"
set "FZF_EXE=%CORE_DIR%\fzf.exe"
set "RUNTIME_DIR=%BASE_DIR%\._runtime"
set "MENU_FILE=%RUNTIME_DIR%\project_menu_ru.txt"
set "RES_FILE=%RUNTIME_DIR%\project_menu_ru_res.txt"

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%" >nul 2>nul
del /f /q "%MENU_FILE%" "%RES_FILE%" >nul 2>nul

call :RESOLVE_PYTHON
if errorlevel 1 goto NO_PYTHON

:MAIN
cls
echo ======================================================================
echo   AUDION ADDRESS ALIGNER - РУССКИЙ ЛАУНЧЕР ПРОЕКТА
echo ======================================================================
echo Корень: %BASE_DIR%
echo Python: %PYTHON_CMD% %PYTHON_ARGS%
echo.

if exist "%FZF_EXE%" goto FZF_MENU
goto FALLBACK_MENU

:FZF_MENU
> "%MENU_FILE%" echo [01] ЗАПУСТИТЬ ВЫРАВНИВАТЕЛЬ АДРЕСОВ ^| run_aligner     ^| выравнивание адресов из input в output
>>"%MENU_FILE%" echo [02] ЗАПУСТИТЬ ДИАГНОСТИКУ ПАРСЕРА   ^| run_diagnostic  ^| извлечь компоненты адреса
>>"%MENU_FILE%" echo [03] ПРАВИТЬ PROJECT YAML            ^| edit_yaml       ^| открыть config\project.yaml
>>"%MENU_FILE%" echo [04] УБРАТЬ ПУСТЫЕ СТРОКИ OUTPUT     ^| clean_rows      ^| создать копии *_no_empty_rows.xlsx
>>"%MENU_FILE%" echo [05] ПРОВЕРКА ОКРУЖЕНИЯ              ^| run_doctor      ^| runtime и импорты
>>"%MENU_FILE%" echo.
>>"%MENU_FILE%" echo [06] СОБРАТЬ PORTABLE ENV CMD        ^| build_cmd       ^| пересобрать runtime через CMD builder
>>"%MENU_FILE%" echo [07] СОБРАТЬ PORTABLE ENV PS         ^| build_ps        ^| дополнительный PowerShell builder
>>"%MENU_FILE%" echo [08] УСТАНОВИТЬ PORTABLE OFFLINE     ^| install_offline ^| локальный runtime плюс wheelhouse
>>"%MENU_FILE%" echo [09] ПРОВЕРИТЬ PORTABLE ENV          ^| verify_env      ^| запустить doctor
>>"%MENU_FILE%" echo [10] ОБНОВИТЬ FZF                    ^| update_fzf      ^| скачать свежий fzf.exe
>>"%MENU_FILE%" echo [11] СОБРАТЬ RELEASE-АРХИВ           ^| make_release    ^| упаковать проект в zip
>>"%MENU_FILE%" echo.
>>"%MENU_FILE%" echo [12] ОТКРЫТЬ ПАПКУ INPUT             ^| open_input      ^| explorer input
>>"%MENU_FILE%" echo [13] ОТКРЫТЬ ПАПКУ OUTPUT            ^| open_output     ^| explorer output
>>"%MENU_FILE%" echo [14] ЛАУНЧЕР ИНСТРУМЕНТОВ            ^| tools           ^| открыть служебное меню
>>"%MENU_FILE%" echo [15] GUI-ОБОЛОЧКА                    ^| gui             ^| открыть NiceGUI
>>"%MENU_FILE%" echo [00] ВЫХОД                           ^| exit            ^| закрыть лаунчер

type "%MENU_FILE%" | "%FZF_EXE%" --prompt="audion@address-processor [PROJECT-RU] > " --pointer=">" --header="Выберите действие:" --layout=reverse --border="rounded" --info=hidden --margin=1,2 > "%RES_FILE%"

set "CHOICE="
set /p CHOICE=<"%RES_FILE%"
if not defined CHOICE goto MAIN

for /f "tokens=2 delims=|" %%a in ("%CHOICE%") do set "RAW=%%a"
call :TRIM RAW

if /I "%RAW%"=="run_aligner"     goto RUN_ALIGNER
if /I "%RAW%"=="run_diagnostic"  goto RUN_DIAGNOSTIC
if /I "%RAW%"=="edit_yaml"       goto EDIT_YAML
if /I "%RAW%"=="clean_rows"      goto CLEAN_ROWS
if /I "%RAW%"=="run_doctor"      goto RUN_DOCTOR
if /I "%RAW%"=="build_cmd"       goto BUILD_CMD
if /I "%RAW%"=="build_ps"        goto BUILD_PS
if /I "%RAW%"=="install_offline" goto INSTALL_OFFLINE
if /I "%RAW%"=="verify_env"      goto VERIFY_ENV
if /I "%RAW%"=="update_fzf"      goto UPDATE_FZF
if /I "%RAW%"=="make_release"    goto MAKE_RELEASE
if /I "%RAW%"=="open_input"      goto OPEN_INPUT
if /I "%RAW%"=="open_output"     goto OPEN_OUTPUT
if /I "%RAW%"=="tools"           goto TOOLS
if /I "%RAW%"=="gui"             goto GUI
if /I "%RAW%"=="exit"            exit /b 0
goto MAIN

:FALLBACK_MENU
echo [1] Запустить выравниватель адресов
echo [2] Запустить диагностику парсера
echo [3] Править project.yaml
echo [4] Убрать пустые строки output
echo [5] Проверка окружения
echo [6] Собрать portable env CMD
echo [7] Собрать portable env PS
echo [8] Установить portable offline
echo [9] Проверить portable env
echo [A] Обновить fzf
echo [B] Собрать release-архив
echo [C] Открыть папку input
echo [D] Открыть папку output
echo [T] Лаунчер инструментов
echo [G] GUI-оболочка
echo [0] Выход
echo.
choice /C 123456789ABCDTG0 /N /M "Выбор: "
if errorlevel 16 exit /b 0
if errorlevel 15 goto GUI
if errorlevel 14 goto TOOLS
if errorlevel 13 goto OPEN_OUTPUT
if errorlevel 12 goto OPEN_INPUT
if errorlevel 11 goto MAKE_RELEASE
if errorlevel 10 goto UPDATE_FZF
if errorlevel 9  goto VERIFY_ENV
if errorlevel 8  goto INSTALL_OFFLINE
if errorlevel 7  goto BUILD_PS
if errorlevel 6  goto BUILD_CMD
if errorlevel 5  goto RUN_DOCTOR
if errorlevel 4  goto CLEAN_ROWS
if errorlevel 3  goto EDIT_YAML
if errorlevel 2  goto RUN_DIAGNOSTIC
if errorlevel 1  goto RUN_ALIGNER
goto MAIN

:RUN_ALIGNER
call :RUNPY "%CORE_DIR%\main.py"
if not defined AUDION_NO_PAUSE pause
goto MAIN

:RUN_DIAGNOSTIC
call :RUNPY "%CORE_DIR%\Parser_Diagnostic.py" "%BASE_DIR%\input" "%BASE_DIR%\output"
if not defined AUDION_NO_PAUSE pause
goto MAIN

:EDIT_YAML
start "" notepad "%BASE_DIR%\config\project.yaml"
goto MAIN

:CLEAN_ROWS
call "%CORE_DIR%\remove_empty_rows.cmd" "%BASE_DIR%\output"
goto MAIN

:RUN_DOCTOR
call :RUNPY "%CORE_DIR%\doctor.py"
if not defined AUDION_NO_PAUSE pause
goto MAIN

:BUILD_CMD
call "%INSTALL_DIR%\Build_Portable_Env_Build.cmd"
goto MAIN

:BUILD_PS
call "%INSTALL_DIR%\Build_Portable_Env.cmd"
goto MAIN

:INSTALL_OFFLINE
call "%INSTALL_DIR%\install_portable_offline.cmd"
goto MAIN

:VERIFY_ENV
call "%INSTALL_DIR%\verify_portable_env.cmd"
goto MAIN

:UPDATE_FZF
call "%INSTALL_DIR%\launcher-tools-update_fzf.cmd"
goto MAIN

:MAKE_RELEASE
call "%INSTALL_DIR%\make_release_archive.cmd"
goto MAIN

:OPEN_INPUT
start "" explorer "%BASE_DIR%\input"
goto MAIN

:OPEN_OUTPUT
start "" explorer "%BASE_DIR%\output"
goto MAIN

:TOOLS
call "%BASE_DIR%\launcher_tools.cmd"
goto MAIN

:GUI
call "%BASE_DIR%\launcher_gui.cmd"
goto MAIN

:NO_PYTHON
cls
echo [ERROR] Python runtime не найден.
echo.
echo Поддерживаемые варианты:
echo   runtime\python.exe
echo   runtime\python\python.exe
echo   py -3.12
echo   python
echo.
echo Используйте builder_main.cmd или install\Build_Portable_Env_Build.cmd
if not defined AUDION_NO_PAUSE pause
exit /b 1

:RUNPY
set "TARGET=%~1"
shift
if not exist "%TARGET%" (
  echo [ERROR] Скрипт не найден:
  echo %TARGET%
  goto :eof
)
"%PYTHON_CMD%" %PYTHON_ARGS% "%TARGET%" %*
goto :eof

:RESOLVE_PYTHON
set "PYTHON_CMD="
set "PYTHON_ARGS="

if exist "%BASE_DIR%\runtime\python.exe" (
  set "PYTHON_CMD=%BASE_DIR%\runtime\python.exe"
  goto PY_OK
)

if exist "%BASE_DIR%\runtime\python\python.exe" (
  set "PYTHON_CMD=%BASE_DIR%\runtime\python\python.exe"
  goto PY_OK
)

py -3.12 -V >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=py"
  set "PYTHON_ARGS=-3.12"
  goto PY_OK
)

where python >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=python"
  goto PY_OK
)

exit /b 1

:PY_OK
exit /b 0

:TRIM
for /f "tokens=* delims= " %%z in ("!%~1!") do set "%~1=%%z"
:TRIM_R
if "!%~1:~-1!"==" " set "%~1=!%~1:~0,-1!" & goto TRIM_R
goto :eof
