# Portable WAV/Media Transcriber — Docs

> Turn a folder of `.wav`/`.mp4` into `.txt` (+ optional `.vtt`) with one click. Local `faster-whisper`, dark suite shell shared with **Clickable Timestamp Recorder**.

**30-sec pitch:** Drop the exe/bat beside media → pick `Large-v3` or `Turbo` + audio track → `Transcribe` → each file gets a same-name `.txt` beside it. First run auto-downloads `ffmpeg (~80MB)` to `.tools/` and the model (`~3GB`/`~1.6GB`) to HF cache; next runs are offline.

- [Overview](overview.md) — who it's for, what it does, limits
- [User Guide](user-guide.md) — GUI + batch walkthrough with screenshots
- [Architecture](architecture.md) — 3 boxes + how a file becomes text
- [Troubleshooting](troubleshooting.md) — fixes for 90% of hiccups

Related: `../README.md` (shipping), `../transcribe_gui.pyw` (CTk shell), `../transcribe_wav.py` (engine), `../Transcribe_GUI.spec` (PyInstaller).

![Dark shell](../App-Picture.png)
