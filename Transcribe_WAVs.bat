@echo off
rem ============================================================
rem  Portable WAV/Media Transcriber - faster-whisper large-v3
rem  Drop this .bat + transcribe_wav.py beside your media files
rem  (.wav/.mp3/.m4a/.flac/.ogg/.aac/.mp4/.mov/.mkv/.webm)
rem  and double-click. One .txt per file in same folder.
rem  Video containers: audio track ordinal 3 ("Track 4") is used by
rem  default - override per run via transcribe_wav.py --stream N.
rem  First run downloads portable ffmpeg to .tools and creates
rem  .venv and downloads large-v3 model ~3GB to HF cache.
rem  NOTE: this file must be saved with Windows CRLF endings.
rem ============================================================

rem --- Crash-proof launcher: all real work runs in a child cmd.
rem     This parent always pauses afterwards, so the window can
rem     never close silently - even if the child hits a parse
rem     level error, its message stays visible on screen. ---
if /i not "%~1"=="__run__" (
    cmd /d /c call "%~f0" __run__
    pause
    exit /b 0
)

setlocal EnableDelayedExpansion
title Portable WAV Transcriber

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

echo ============================================================
echo   Portable WAV/Media Transcriber  -  faster-whisper large-v3
echo   Drop this .bat + transcribe_wav.py beside your media files
echo   then double-click. One .txt per file in same folder.
echo   Videos: audio track 3 (Track 4) by default, see --stream.
echo ============================================================
echo.
echo Folder: %SCRIPT_DIR%
echo.

rem --- Find Python: prefer py launcher, skip MS Store stub ---
set "PY_CMD="
where py >nul 2>nul
if !ERRORLEVEL!==0 (
    py -3 --version >nul 2>nul
    if !ERRORLEVEL!==0 set "PY_CMD=py -3"
)
if "!PY_CMD!"=="" (
    set "PY_CANDIDATE="
    for /f "tokens=*" %%p in ('where python 2^>nul') do (
        if not defined PY_CANDIDATE (
            set "PY_PATH=%%p"
            if "!PY_PATH:WindowsApps=!"=="!PY_PATH!" set "PY_CANDIDATE=%%p"
        )
    )
    if defined PY_CANDIDATE (
        "!PY_CANDIDATE!" --version >nul 2>nul
        if !ERRORLEVEL!==0 set "PY_CMD=!PY_CANDIDATE!"
    )
)
if "!PY_CMD!"=="" (
    echo ERROR: Python 3.10+ not found.
    echo Install from https://www.python.org/downloads/
    echo Make sure to check "Add python.exe to PATH" during install.
    echo Or run: winget install Python.Python.3.11
    exit /b 1
)
echo Found Python: !PY_CMD!
for /f "tokens=*" %%v in ('!PY_CMD! --version 2^>^&1') do echo   %%v
echo.

rem --- Check Python is 3.10 or newer ---
!PY_CMD! -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo ERROR: Python 3.10 or newer required. Found older version.
    echo Update from https://www.python.org/downloads/
    exit /b 1
)

rem --- venv bootstrap ---
set "VENV_PY=%SCRIPT_DIR%\.venv\Scripts\python.exe"
set "VENV_PIP=%SCRIPT_DIR%\.venv\Scripts\pip.exe"
if exist "%VENV_PY%" (
    echo Virtual env exists: .venv
) else (
    echo Creating virtual environment in .venv ...
    !PY_CMD! -m venv "%SCRIPT_DIR%\.venv"
    if !ERRORLEVEL! NEQ 0 (
        echo ERROR: Failed to create venv. Check Python install and disk space.
        exit /b 1
    )
    echo Upgrading pip...
    "%VENV_PY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
    if !ERRORLEVEL! NEQ 0 echo WARNING: pip upgrade failed, continuing...
)
echo.

rem --- ffmpeg bootstrap: portable build in .tools, session PATH only ---
set "TOOLS_DIR=%SCRIPT_DIR%\.tools"
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"
set "PATH=%TOOLS_DIR%;%PATH%"
call :ensure_ffmpeg
if !ERRORLEVEL! NEQ 0 (
    echo ERROR: ffmpeg setup failed.
    echo You can manually place ffmpeg.exe into %TOOLS_DIR%
    echo Get it from https://www.gyan.dev/ffmpeg/builds/ or https://github.com/BtbN/FFmpeg-Builds/releases
    exit /b 1
)
echo.

rem --- pip deps: skip if already installed ---
"%VENV_PY%" -c "import faster_whisper" >nul 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo Installing faster-whisper stack - first run only, 1-2 minutes...
    echo   faster-whisper, soundfile, av, numpy, customtkinter
    "%VENV_PIP%" install --upgrade faster-whisper soundfile av numpy customtkinter --quiet --disable-pip-version-check
    if !ERRORLEVEL! NEQ 0 (
        echo ERROR: pip install failed. Check internet and disk space.
        echo Try manually: .venv\Scripts\pip install faster-whisper soundfile av numpy customtkinter
        exit /b 1
    )
    echo Dependencies installed.
) else (
    echo Dependencies already installed.
)
echo.

rem --- Check transcribe_wav.py exists ---
if not exist "%SCRIPT_DIR%\transcribe_wav.py" (
    echo ERROR: transcribe_wav.py not found beside this .bat
    echo Make sure both files are in the same folder: %SCRIPT_DIR%
    exit /b 1
)

rem --- Scan for media files ---
set /a count=0
for %%f in ("%SCRIPT_DIR%\*.wav" "%SCRIPT_DIR%\*.mp3" "%SCRIPT_DIR%\*.m4a" "%SCRIPT_DIR%\*.flac" "%SCRIPT_DIR%\*.ogg" "%SCRIPT_DIR%\*.aac" "%SCRIPT_DIR%\*.mp4" "%SCRIPT_DIR%\*.mov" "%SCRIPT_DIR%\*.mkv" "%SCRIPT_DIR%\*.webm") do (
    if exist "%%f" set /a count+=1
)
if %count%==0 (
    echo No media files found in:
    echo   %SCRIPT_DIR%
    echo.
    echo Supported: .wav .mp3 .m4a .flac .ogg .aac .mp4 .mov .mkv .webm
    exit /b 0
)
echo Found %count% media file(s) in %SCRIPT_DIR%
echo.

rem --- Transcribe sequentially, one at a time - no parallel VRAM contention ---
set /a success=0
set /a skipped=0
set /a failed=0

for %%f in ("%SCRIPT_DIR%\*.wav" "%SCRIPT_DIR%\*.mp3" "%SCRIPT_DIR%\*.m4a" "%SCRIPT_DIR%\*.flac" "%SCRIPT_DIR%\*.ogg" "%SCRIPT_DIR%\*.aac" "%SCRIPT_DIR%\*.mp4" "%SCRIPT_DIR%\*.mov" "%SCRIPT_DIR%\*.mkv" "%SCRIPT_DIR%\*.webm") do (
    if exist "%%f" (
        rem Skip/existing-output logic (incl. _sN suffixed names for video
        rem tracks) is handled inside transcribe_wav.py per file.
        echo ------------------------------------------------------------
        echo START: %%~nxf
        echo ------------------------------------------------------------
        "%VENV_PY%" "%SCRIPT_DIR%\transcribe_wav.py" "%%f" --model large-v3 --compute auto
        if !ERRORLEVEL!==0 (
            echo DONE: %%~nxf
            set /a success+=1
        ) else (
            echo FAILED: %%~nxf - see error above
            set /a failed+=1
        )
        echo.
    )
)

echo.
echo ============================================================
echo   Finished: !success! transcribed, !failed! failed out of !count!
echo   .txt files are beside each media file in:
echo   %SCRIPT_DIR%
echo ============================================================
echo.
echo Tip: delete a .txt to re-transcribe that file next run.
echo Tip: model large-v3 is cached in %USERPROFILE%\.cache\huggingface
endlocal
exit /b 0

:ensure_ffmpeg
where ffmpeg >nul 2>nul
if !ERRORLEVEL!==0 (
    echo Found ffmpeg on PATH.
    exit /b 0
)
if exist "%TOOLS_DIR%\ffmpeg.exe" (
    echo Found portable ffmpeg in .tools\
    exit /b 0
)
echo ffmpeg not found - downloading portable build, about 80MB, one time...
set "FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
set "FFMPEG_ZIP=%TOOLS_DIR%\ffmpeg.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '!FFMPEG_URL!' -OutFile '!FFMPEG_ZIP!' -UseBasicParsing"
if !ERRORLEVEL! NEQ 0 (
    echo ERROR: ffmpeg download failed. Check internet connection.
    del "!FFMPEG_ZIP!" >nul 2>nul
    exit /b 1
)
echo Download complete - extracting...
powershell -NoProfile -Command "Expand-Archive -Path '!FFMPEG_ZIP!' -DestinationPath '%TOOLS_DIR%' -Force"
powershell -NoProfile -Command "$exe = Get-ChildItem -Path '%TOOLS_DIR%' -Recurse -Filter ffmpeg.exe | Select-Object -First 1; if ($exe) { Copy-Item $exe.FullName '%TOOLS_DIR%\ffmpeg.exe' -Force }; $probe = Get-ChildItem -Path '%TOOLS_DIR%' -Recurse -Filter ffprobe.exe | Select-Object -First 1; if ($probe) { Copy-Item $probe.FullName '%TOOLS_DIR%\ffprobe.exe' -Force }"
del "!FFMPEG_ZIP!" >nul 2>nul
powershell -NoProfile -Command "Get-ChildItem -Path '%TOOLS_DIR%' -Directory | Where-Object { $_.Name -like 'ffmpeg*' } | Remove-Item -Recurse -Force"
if not exist "%TOOLS_DIR%\ffmpeg.exe" (
    echo ERROR: ffmpeg.exe missing after extraction.
    exit /b 1
)
echo ffmpeg installed to .tools\ffmpeg.exe
exit /b 0
