# Troubleshooting

## 1-min checklist before filing

- Folder path pasted correctly? Try `Browse…` to normalize it (trims quotes, expands `~`).
- Top level only — files in subfolders are not scanned by design.
- Writable folder? Don’t run the exe from `Program Files`, a locked OneDrive sync, or a zip preview.
- First run? Needs internet + ~5GB free (`.tools` + model + temp wav).

| Symptom | Fix |
|---|---|
| `Folder not found` | Use `Browse…`; path is absolutized — check drive letter and quotes. |
| `No supported media files` | Supported `wav mp3 m4a flac ogg aac mp4 mov mkv webm` — top level only. |
| `Engine import failed` / `Setup not complete` | Source run: double-click `Transcribe_WAVs.bat` once (creates `.venv` + installs `faster-whisper soundfile av numpy customtkinter`). Bat retries `venv` vs current Python. |
| `ffmpeg download failed` | Check internet; manual fix: drop `ffmpeg.exe` (+ `ffprobe.exe`) into `.tools/` from https://www.gyan.dev/ffmpeg/builds/ or BtbN releases. Up to `80MB` download. |
| `pip install failed` | Disk/internet; manual: `.venv\Scripts\pip install faster-whisper soundfile av numpy customtkinter` or `python -m pip install …`. |
| Wrong transcript on video | Track mismatch — game audio vs VO. Try other `Stream N` in GUI dropdown or CLI `python transcribe_wav.py folder --stream N` / `--stream -1` (Auto). Engine clamps OOR with `NOTE:` and uses `_sN` suffix. |
| `Out of memory / CUDA / cublas` | Auto fallback `cuda float16 → cuda int8_float16 → cpu int8`. Close VRAM hogs or pick `Turbo`. |
| Progress stuck / `Cancel` | `Cancel` finishes **current file** then stops by design; reopen GUI if header stays `Working`. |
| Want overwrite | Delete the output(s) — `.txt` and/or `.vtt`, e.g. `video_s4.txt` — or CLI `python transcribe_wav.py "file.wav" --force --vtt`. `SKIPPED` means the `.txt` **or** `.vtt` output for the selected track already exists. |
| SmartScreen `protected your PC` | `More info → Run anyway`; unblock `.bat` via `Properties → Unblock`. |
| `GUI says Setup not complete` after bat | Wait for bat `Finished:` line; relaunch exe. If still stuck, `py --version` ≥ 3.10? |
| Rebuild exe fails | `.venv\Scripts\pyinstaller --noconfirm Transcribe_GUI.spec` (or `build_exe.bat` — auto-installs `customtkinter`+`pyinstaller` if missing) → `dist/Transcribe_GUI.exe ~94MB`, `--noconsole`. |

## Diagnostic commands

```bat
python --version
.venv\Scripts\python -c "import faster_whisper,customtkinter,av; print('ok')"
.venv\Scripts\python -m py_compile transcribe_gui.pyw transcribe_wav.py
Transcribe_WAVs.bat
python transcribe_wav.py "E:\path\to\folder" --stream 3 --vtt
```

## Where things live

- `.tools/ffmpeg.exe` — beside exe/bat (portable).
- `.venv/` — beside source (ignore in git).
- `%USERPROFILE%\.cache\huggingface` — global model cache; delete to force re-download.
- Outputs — `same-name.txt` beside each input; video non-default `_s4.txt` + `_s4.vtt` if VTT enabled.
- Logs — dark `CTkTextbox` in GUI; bat shows live stdout.
