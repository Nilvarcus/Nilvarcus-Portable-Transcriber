# Architecture

## Runtime shape — 3 boxes

```
┌─ App (transcribe_gui.pyw — CTk shell, 700×540) ──────────┐
│  Theme (BG_DARKEST/SURFACE/ENTRY, CRIMSON/BLUE/GREY)      │
│  header(Title+dot) / controls(Folder+Model+VTT+Track)     │
│  main(Transcribe/Open + Progress+Counter + Log) / footer  │
│  queue: msg_queue + after(100) poll + cancel_event        │
└──────────────┬───────────────────────┬────────────────────┘
               │ probe/track            │ transcribe
               ▼                        ▼
        transcribe_wav (engine)   .tools/ffmpeg.exe  ← portable dl
               │
               ▼
        faster-whisper + HF cache (~3GB large-v3)
```

## Module responsibilities

| File | Role |
|---|---|
| `transcribe_gui.pyw` | Window, `Theme`, `normalize_folder`, `check_bootstrap`, `ensure_ffmpeg`, `ensure_source_deps`, thread + `queue` (`log/status/progress/done`) + `after` polling, `CTkTextbox` smart-follow (`yview>=0.98`) |
| `transcribe_wav.py` | `probe_audio_streams` (PyAV, no `ffprobe`), `resolve_track` (`_sN` suffix), `extract_audio_ffmpeg` (`-map 0:a:N` → 16k mono), `load_model` (auto `float16→int8_float16→int8`), `filter_*` + style anchor, `transcribe_file` → `write_txt/write_vtt` |
| `Transcribe_GUI.spec` | Bundles `customtkinter` dir + `faster_whisper/assets/silero_vad_v6.onnx` (VAD would fail without it) |
| `build_exe.bat` / `Transcribe_WAVs.bat` | Bat bootstrap — crash-proof `__run__` wrapper (CRLF), venv + deps + ffmpeg + model fetch |

## How a file becomes text (one file)

```
Browse → _on_folder_change → _inspect_tracks (probe first video, fill OptionMenu)
Transcribe → _run_job (background Thread, daemon):
  ensure_source_deps (source only) → filter_pending (partition: skip names via
    resolve_track, so they match the write names incl. `_sN` suffix)
  → nothing pending: done without ffmpeg/model work
  → ensure_ffmpeg (which/.tools/dl) → load_model (cached, redirect_stdout → log)
  for each pending file top-level:
    status "Transcribing X" → extract (wav passthrough else temp wav via ffmpeg) → whisper → filters → write .txt (+ .vtt) → DONE/FAILED → progress++
  done → status "Finished: X transcribed, Y skipped, Z failed"
                ↕ msg_queue
UI thread _poll_queue → _set_progress / _log / _set_status (dot color + footer mirror)
```

## Key decisions & invariants

- **No engine change** in this reskin — `transcribe_wav.py` untouched; GUI only consumes it.
- **Top-level only** scan (`os.listdir`, no `rglob`); skips a file if its `.txt` **or** `.vtt` output (resolved, `_sN`-aware name for the selected track) already exists — shared `filter_pending` in the engine, no GUI-side duplicate name math; per-file error never aborts whole run (worker `try/except` per file).
- **Header dot** derived from status text (`Working`=`AMBER`, `Done`=`GREEN`, `Error`=`RED`, `Ready`=`GREEN`, `Idle`=`GREY`).
- **Windowed exe** guard: `sys.stdout=None` → `io.StringIO` dummy; engine prints captured via `redirect_stdout` so VAD/model logs surface in GUI even with `console=False`.
- **`SCRIPT_DIR`** = `sys.executable` dir when `frozen`, else `.pyw` dir; `.tools` added to `PATH` early so `ffmpeg` is found before bootstrap.
- **Artifacts:** `.venv/`, `.tools/`, `build/`, `dist/`, `__pycache__/` ignored (`/.gitignore`); HF cache is global (`~/.cache/huggingface`); outputs live **beside sources** (`video_s4.txt` for non-default tracks).

## Data flow

Input folder → `MEDIA_EXTS` list → per-file `(streams, eff_stream, out_base)` via `resolve_track` → temp wav if needed → `model.transcribe` → `filter_hallucinations/repeat/fragments` + style retry → `write_txt` (`out_base.txt`) + `write_vtt` if flagged. All `print()` is queue-routed, never direct `Tk` mutation from worker.
