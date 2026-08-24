# Overview

## In one line
Local, portable transcriber: any folder of `wav/mp3/m4a/flac/ogg/aac/mp4/mov/mkv/webm` → one `.txt` (and optional `.vtt`) per file, written beside the source. No cloud upload after the first model download.

## Who it's for
Game commentary / voiceover capture where the DaVinci "Track 4 = VO" convention matters, and you want no cloud upload after the first model download. Pairs visually with **Clickable Timestamp Recorder** — same `Theme`, rounded frames, and fonts so both apps feel like a suite.

## What it does (current capabilities)
- **Dark suite shell** — `customtkinter` `700×540` (min `620×440`), `Theme` copied from Clickable (`BG_DARKEST #0A0A0A` / `BG_SURFACE #141414` / `BG_ENTRY #1A1A1A`, `Segoe UI`, `r=12/8`, `CRIMSON` primary, `BLUE` browse). Header dot = `Idle / Ready / Working / Done / Error`.
- **Two entry points** — `Transcribe_GUI.exe` / `transcribe_gui.pyw` (CTk window, no console) and `Transcribe_WAVs.bat` (one-click console batch).
- **Video-aware** — picks one audio track via `PyAV` probe + `ffmpeg -map 0:a:N`; defaults to `Stream 3 (Track 4)`, `Auto` = container default, `_sN` suffix avoids collisions on multi-track containers.
- **Two models** — `Large-v3` (best) vs `Turbo` (fast, ~8×); auto compute `cuda float16 → cuda int8_float16 → cpu int8` with Silero VAD and hallucination/repeat/fragment filters.
- **Self-bootstrapping** — portable `ffmpeg` to `.tools/`, `faster-whisper/soundfile/av/numpy/customtkinter` to `.venv` (source path), models to `%USERPROFILE%\.cache\huggingface` (reused).

## How it feels (30 sec)
Pick a folder → header turns `● Ready · N files` → pick model/track → `Transcribe` → `CTkProgressBar` fills `3 / 13 — file.mp4` and the dark `CTkTextbox` logs `SKIPPED`/`DONE`/`FAILED` with smart-follow. `Cancel` drains after current file. `Open folder` reveals the `.txt` files.

## Deliberate limits
- Windows 10/11 primary; mac/Linux not targeted.
- Folder scan = top level only, not recursive.
- One job at a time (queue + `Cancel` after current file).
- No cloud, no database, no editing — just files beside files.
- Windowed exe has no console: all `print()` is redirected to the log (`io.StringIO` dummy + `redirect_stdout`).
- First run needs internet + ~5GB free; next runs are offline.
