# User Guide

![Dark shell](../App-Picture.png)

## Quick start — GUI (2 min)

1. **Unzip anywhere writable** (not `Program Files` — `.tools/` needs write). Keep `Transcribe_GUI.exe` + `Transcribe_WAVs.bat` + `transcribe_wav.py` together for the zip path; **exe alone** is enough for the exe path (no Python needed).
2. Double-click `Transcribe_GUI.exe` (no console). Dark window appears — header shows `● Idle`.
3. **Folder** — paste path or click `Browse…` → header turns `● Ready · N files` and the **Audio track** dropdown auto-fills from the first video (codec/ch/lang shown).
4. **Model** — `Large-v3 (best, ~3GB)` or `Turbo (fast, ~1.6GB)`; tick `Also write .vtt` if you need `WEBVTT` subtitles.
5. **Audio track (videos)** — leave `Stream 3 (Track 4)` for DaVinci VO, or pick `Auto — container default` / another stream. Single-track files and `.wav`s ignore it; non-default tracks write `video_s4.txt` so outputs never collide.
6. **Transcribe** — `CRIMSON` button → `● Working`, `CTkProgressBar` + `3 / 13 — R02-004.wav` counter, log shows `SKIPPED` (already has `.txt`) / `DONE` / `FAILED` per file. Click `Cancel` (turns `GREY`) to stop after current file.
7. **Open folder** — jumps to the folder with the new `.txt` (and `.vtt`) files. Delete a `.txt` to re-transcribe that file next run. Resize the window as needed (`min 620×440`).

> First run says `Setup not complete`? Double-click `Transcribe_WAVs.bat` once, wait for `Finished: X transcribed`, then relaunch the GUI. Never run the exe from a cloud-synced temp folder on first run (OneDrive locks `.tools`).

## One-click batch — no GUI

1. Put `Transcribe_WAVs.bat` + `transcribe_wav.py` beside your media files.
2. Double-click the bat. It reuses the same track default (`--stream 3`); edit that flag inside the bat to change it.
3. Console stays open — `START → DONE/FAILED` per file, summary `Finished: X transcribed, Y skipped, Z failed`.

## Video track details

- Dropdown defaults to **Stream 3 (Track 4)** — the DaVinci VO convention, populated by probing the first video via `PyAV` (`probe_audio_streams`). Shows `Stream i (Track i+1) — codec, ch, [lang] title`.
- If the chosen ordinal exceeds a file's stream count, the engine clamps to the last stream with a `NOTE:` and still writes with `_sN` suffix.
- CLI: `python transcribe_wav.py "folder" --stream 2` (0-based), `--stream -1` = `Auto`.

## Model & output notes

- **VTT:** `Also write .vtt` or CLI `--vtt` → `WEBVTT` with `HH:MM:SS.mmm -->`.
- **Other models:** GUI offers two; engine accepts any `faster-whisper` name via CLI `--model large-v3-turbo / distil-large-v3 / small.en …`.
- **Prompt/terms:** edit `DEFAULT_PROMPT` or CLI `--prompt "Sentence." --terms "BossName, Item"` for jargon.
- **Cache:** models live in `%USERPROFILE%\.cache\huggingface` (global, not per folder). Delete that folder to force re-download.

## When to use which

- **GUI** for interactive work (progress + track picker + cancel).
- **Batch bat** for headless folders or for recipients who just double-click.
