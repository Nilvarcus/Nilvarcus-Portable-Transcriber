# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-24

Initial public release of **Portable WAV/Media Transcriber** — one-click local transcription via `faster-whisper`.

### Added
- **Dark suite GUI** (`Transcribe_GUI.exe` / `transcribe_gui.pyw`, 700×540, `customtkinter`) — Folder picker, model toggle (Large-v3 best ~3GB / Turbo fast ~1.6GB), `Also write .vtt`, video **Audio track** dropdown (defaults to Stream 3 / Track 4 — DaVinci VO convention, probed via PyAV), progress bar + counter (`3 / 13 — file.wav`), smart-follow log, Cancel/Open folder. No console window.
- **One-click batch** (`Transcribe_WAVs.bat` + `transcribe_wav.py`) — drop beside media and double-click; auto bootstraps portable `ffmpeg` to `.tools/`, deps to `.venv`, models to `%USERPROFILE%\.cache\huggingface` (offline next runs).
- **Video-aware engine** (`transcribe_wav.py`) — extracts one audio track via `ffmpeg -map 0:a:N` (16k mono), clamps OOR streams, writes suffixed outputs (`video_s4.txt`) to avoid collisions; top-level scan only, skips existing `.txt`, per-file error never aborts batch.
- **Whisper pipeline** — `faster-whisper` auto compute `cuda float16 → cuda int8_float16 → cpu int8`, Silero VAD, hallucination/repeat/fragment filters + style-anchor retry.
- **Outputs** — one `.txt` per file beside source, optional `.vtt` (`WEBVTT HH:MM:SS.mmm -->`) via GUI checkbox / `--vtt`.
- **CLI flags** — `--model`, `--stream N` (`-1` = Auto), `--compute auto`, `--prompt`/`--terms`, `--force`, `--no-vad`, etc.
- **Build** — `Transcribe_GUI.spec` (bundles `customtkinter` + `silero_vad_v6.onnx`) + `build_exe.bat` → `dist/Transcribe_GUI.exe` (~94MB, `--noconsole`).
- **Docs** — lean `README.md` with hero screenshot (`App-Picture.png`), `doc/overview.md`, `doc/user-guide.md`, `doc/architecture.md`, `doc/troubleshooting.md`.
- **Tests** — fixtures in `tests/` (`R02-004_00-00-04*.wav`).

### Changed
- `README.md` rewritten from ~140 → 31 lines: hero image on top, 3-step Quick start, Requirements + Notes, links to `doc/` for full detail.

### Packaging
- Release asset: `release/1.0.0/Transcribe_GUI-1.0.0.zip` — contains `Transcribe_GUI.exe` (93.74 MB unpacked, SHA256 `392D6A8AAC394FD065CDEA9E7DD2636DFCE54C0B2EAC2E8367240C735DBD5567`). Repo-local only (`release/` is gitignored); publish via GitHub Releases.
- `.gitignore` — expanded to cover `.venv/`, `.tools/`, `dist/`, `build/`, caches (`.pytest_cache/` etc.), OS/editor files, `nul` accident file, and media/transcript outputs (`*.wav`/`*.mp4`/`*.vtt` with `!tests/*.wav` re-allow).

[1.0.0]: https://github.com/Nilvarcus/Nilvarcus-Portable-Transcriber/releases/tag/v1.0.0

## [1.0.1] - 2026-10-14

### Fixed
- **No more re-transcribing finished files** — the GUI worker checked only the plain `video.txt` name while the engine writes `video_s4.txt` (+ `video_s4.vtt`) for non-default tracks of multi-stream containers (Track 4 is the GUI default), so those videos re-transcribed on every run. Skip logic now lives in one shared, track-aware resolver (`output_paths` / `existing_output` / `filter_pending` in `transcribe_wav.py`) used by both the GUI and the CLI — the skip name always equals the write name.
- **`.vtt` counts as done** — a file is skipped if its `.txt` **or** `.vtt` output already exists (previously `.vtt` was never considered). CLI `--force` still bypasses both.
- **Skip before model load** — partitioning happens before ffmpeg/model setup: a folder where every file already has outputs finishes instantly ("All N file(s) already have outputs") without loading the 3GB model (GUI and CLI).
- **Reverted** an uncommitted change that had removed the documented `_sN` output suffix (contradicted the docs and left existing `_sN` outputs invisible to skip checks).
- Track switching still works: skipping checks only the *selected* track's names, so a `video_s4.txt` (Track 4) doesn't block re-running for Track 2 into `video_s2.txt`.

### Packaging
- Release asset: `release/1.0.1/Transcribe_GUI-1.0.1.zip` — contains `Transcribe_GUI.exe` (93.74 MB unpacked, SHA256 `5F660F8EFCE5F3CAB992A94FE1AA0DC850E20A67A9C6D019410C30A927550D32`). Repo-local only (`release/` is gitignored); publish via GitHub Releases.
