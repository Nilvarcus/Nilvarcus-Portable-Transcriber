@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
echo Building Transcribe_GUI.exe with PyInstaller...
echo Folder: %SCRIPT_DIR%
echo.

rem Ensure .venv exists (reuse batch's bootstrap check)
if not exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    echo ERROR: .venv not found. Run Transcribe_WAVs.bat once first to create it.
    pause
    exit /b 1
)

"%SCRIPT_DIR%\.venv\Scripts\python.exe" -m pip show customtkinter >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Installing CustomTkinter into .venv...
    "%SCRIPT_DIR%\.venv\Scripts\pip.exe" install customtkinter
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: pip install customtkinter failed.
        pause
        exit /b 1
    )
)

"%SCRIPT_DIR%\.venv\Scripts\python.exe" -m pip show pyinstaller >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Installing PyInstaller into .venv...
    "%SCRIPT_DIR%\.venv\Scripts\pip.exe" install pyinstaller
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: pip install pyinstaller failed.
        pause
        exit /b 1
    )
)

echo Running PyInstaller...
"%SCRIPT_DIR%\.venv\Scripts\pyinstaller.exe" --noconfirm "%SCRIPT_DIR%\Transcribe_GUI.spec"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PyInstaller failed.
    pause
    exit /b 1
)

echo.
echo Build complete: %SCRIPT_DIR%\dist\Transcribe_GUI.exe
dir "%SCRIPT_DIR%\dist\Transcribe_GUI.exe"
echo.
echo Tip: copy Transcribe_GUI.exe + Transcribe_WAVs.bat + transcribe_wav.py
echo      + transcribe_gui.pyw beside your .wav files, or just the exe
echo      if .venv/.tools are already beside it.
pause
endlocal
