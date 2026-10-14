#!/usr/bin/env python3
"""
Portable WAV/Media Transcriber — CustomTkinter GUI (Clickable shell)

Paste/browse a folder, transcribe its WAVs/videos in place with an overall
progress bar. Reuses transcribe_wav.py engine.

Dark UX shell copied from Clickable-Timestamp-Recorder so both apps feel
like a suite: rounded header/surface frames, unified Theme, CTkProgressBar
+ CTkTextbox log, resizable window.

Video containers (.mp4/.mov/.mkv/.webm) are supported — the engine
extracts the chosen audio track via ffmpeg (-map 0:a:N). The "Audio track"
dropdown defaults to Stream 3 ("Track 4" VO convention) and is populated by
probing the first video in the folder. Model toggle: Large-v3 (best quality)
or Turbo (fast).

exe is self-bootstrapping — first run auto-downloads portable ffmpeg (~80MB)
to .tools beside the exe and reuses it. Models are cached to HF cache on
first transcription and reused (large-v3 ~3GB, turbo ~1.6GB).

PyInstaller frozen detection: SCRIPT_DIR is sys.executable dir when frozen,
otherwise the .pyw dir.
"""
import os
import sys
import threading
import queue
import subprocess
import shutil
import urllib.request
import zipfile
import io
import contextlib


def get_app_dir() -> str:
    """Return folder that should hold .tools / .venv beside the app."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))


SCRIPT_DIR = get_app_dir()
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

_tools_early = os.path.join(SCRIPT_DIR, ".tools")
if os.path.isdir(_tools_early) and _tools_early not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _tools_early + os.pathsep + os.environ.get("PATH", "")

if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

try:
    import transcribe_wav  # noqa: F401
    ENGINE_AVAILABLE = True
    ENGINE_ERROR = ""
except Exception as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)

MEDIA_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac",
              ".mp4", ".mov", ".mkv", ".webm")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")
DEFAULT_TRACK_ORDINAL = 3
FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"


class Theme:
    BG_DARKEST = "#0A0A0A"
    BG_SURFACE = "#141414"
    BG_ENTRY = "#1A1A1A"
    CRIMSON = "#DC143C"
    CRIMSON_HOVER = "#B8112F"
    GREEN = "#00E676"
    GREEN_HOVER = "#00C853"
    BLUE = "#448AFF"
    BLUE_HOVER = "#2962FF"
    RED = "#FF5252"
    RED_HOVER = "#D32F2F"
    AMBER = "#FFAB00"
    GREY = "#616161"
    GREY_HOVER = "#424242"
    VIOLET = "#AB47BC"
    VIOLET_HOVER = "#8E24AA"
    TEXT_DIM = "#AAAAAA"
    TEXT_BRIGHT = "#FFFFFF"
    BTN_SURFACE = "#1C1C1E"
    BTN_SURFACE_HOVER = "#2C2C2E"
    DIVIDER = "#2A2A2A"
    FONT_FAMILY = "Segoe UI"
    FONT_TITLE = (FONT_FAMILY, 16, "bold")
    FONT_SUBTITLE = (FONT_FAMILY, 13, "bold")
    FONT_BODY = (FONT_FAMILY, 12)
    FONT_ROW = (FONT_FAMILY, 11)
    FONT_SMALL = (FONT_FAMILY, 10)
    FONT_BUTTON = (FONT_FAMILY, 12, "bold")
    FONT_BUTTON_SMALL = (FONT_FAMILY, 11)


def normalize_folder(path_str: str) -> str:
    if not path_str:
        return ""
    s = path_str.strip().strip('"').strip("'").strip()
    if not s:
        return ""
    s = os.path.expanduser(s)
    try:
        s = os.path.abspath(s)
    except Exception:
        pass
    return s


def check_bootstrap(script_dir: str):
    if getattr(sys, 'frozen', False):
        if not ENGINE_AVAILABLE:
            return False, (
                f"Bundled engine missing: {ENGINE_ERROR}\n\n"
                "The exe was built without dependencies. Rebuild with:\n"
                "  .venv\\Scripts\\pyinstaller Transcribe_GUI.spec"
            )
        return True, ""
    venv_py = os.path.join(script_dir, ".venv", "Scripts", "python.exe")
    try:
        import faster_whisper  # noqa: F401
        has_current = True
    except Exception:
        has_current = False
    if not has_current and not os.path.isfile(venv_py):
        return False, (
            "Setup not complete — .venv not found and faster_whisper not installed in this Python.\n\n"
            "The GUI will try to create .venv and install dependencies automatically when you\n"
            "click Transcribe. Or double-click Transcribe_WAVs.bat once, then relaunch the GUI.\n"
            "Requires internet and Python 3.10+."
        )
    if not has_current:
        try:
            r = subprocess.run(
                [venv_py, "-c", "import faster_whisper"],
                capture_output=True, timeout=10,
            )
            if r.returncode != 0:
                return False, (
                    "Setup not complete — Python dependencies not installed in .venv.\n\n"
                    "The GUI will try to install them automatically on Transcribe, or run:\n"
                    "  Transcribe_WAVs.bat\n"
                    "once, then relaunch."
                )
        except Exception as e:
            return False, f"Could not probe .venv Python: {e}"
    return True, ""


def ensure_ffmpeg(script_dir: str, log_fn=None, status_fn=None):
    def _log(m):
        if log_fn:
            log_fn(m)
        else:
            try:
                print(m)
            except Exception:
                pass
    def _status(m):
        if status_fn:
            status_fn(m)
    if shutil.which("ffmpeg") is not None:
        _log("Found ffmpeg on PATH.")
        return True
    tools_dir = os.path.join(script_dir, ".tools")
    ffmpeg_exe = os.path.join(tools_dir, "ffmpeg.exe")
    ffprobe_exe = os.path.join(tools_dir, "ffprobe.exe")
    if os.path.isfile(ffmpeg_exe):
        if tools_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = tools_dir + os.pathsep + os.environ.get("PATH", "")
        _log(f"Found portable ffmpeg in {tools_dir}")
        return True
    os.makedirs(tools_dir, exist_ok=True)
    zip_path = os.path.join(tools_dir, "ffmpeg.zip")
    _log("ffmpeg not found — downloading portable build (~80MB, one time)...")
    _status("Downloading ffmpeg (~80MB)...")
    try:
        def _download_with_progress(url, dest, chunk=1024*256):
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
                total = resp.getheader("Content-Length")
                total = int(total) if total and total.isdigit() else 0
                done = 0
                last_pct = -1
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    out.write(data)
                    done += len(data)
                    if total:
                        pct = int(done * 100 / total)
                        if pct != last_pct and pct % 10 == 0:
                            _log(f"  ffmpeg download {pct}% ({done//1048576}MB / {total//1048576}MB)")
                            last_pct = pct
                _log(f"  ffmpeg download complete ({done//1048576}MB)")
        _download_with_progress(FFMPEG_URL, zip_path)
        if os.path.getsize(zip_path) < 1_000_000:
            with open(zip_path, "rb") as f:
                head = f.read(500)
            if b"<html" in head.lower() or b"not found" in head.lower():
                raise RuntimeError("Download returned HTML error page — check internet / GitHub availability.")
        _log("Extracting ffmpeg...")
        _status("Extracting ffmpeg...")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tools_dir)
        import pathlib
        found_ffmpeg = None
        found_probe = None
        for p in pathlib.Path(tools_dir).rglob("ffmpeg.exe"):
            if p.parent == pathlib.Path(tools_dir):
                found_ffmpeg = p
                break
            found_ffmpeg = p
            break
        for p in pathlib.Path(tools_dir).rglob("ffprobe.exe"):
            if p.parent == pathlib.Path(tools_dir):
                found_probe = p
                break
            found_probe = p
            break
        if found_ffmpeg and str(found_ffmpeg) != ffmpeg_exe:
            shutil.copy2(str(found_ffmpeg), ffmpeg_exe)
        if found_probe and str(found_probe) != ffprobe_exe:
            shutil.copy2(str(found_probe), ffprobe_exe)
        try:
            os.remove(zip_path)
        except Exception:
            pass
        for child in os.listdir(tools_dir):
            full = os.path.join(tools_dir, child)
            if os.path.isdir(full):
                try:
                    shutil.rmtree(full)
                except Exception:
                    pass
        if not os.path.isfile(ffmpeg_exe):
            raise RuntimeError("ffmpeg.exe missing after extraction")
        if tools_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = tools_dir + os.pathsep + os.environ.get("PATH", "")
        _log(f"ffmpeg installed to {ffmpeg_exe}")
        _status("ffmpeg ready")
        return True
    except Exception as e:
        _log(f"ERROR: ffmpeg download/setup failed: {e}")
        import traceback as _tb
        _log(_tb.format_exc().strip())
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            pass
        _status("ffmpeg download failed")
        return False


def ensure_source_deps(script_dir: str, log_fn=None, status_fn=None):
    if getattr(sys, 'frozen', False):
        return True
    def _log(m):
        if log_fn:
            log_fn(m)
        else:
            try:
                print(m)
            except Exception:
                pass
    def _status(m):
        if status_fn:
            status_fn(m)
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        pass
    venv_py = os.path.join(script_dir, ".venv", "Scripts", "python.exe")
    venv_pip = os.path.join(script_dir, ".venv", "Scripts", "pip.exe")
    if not os.path.isfile(venv_py):
        _log("Creating virtual environment in .venv ...")
        _status("Creating .venv...")
        try:
            subprocess.run([sys.executable, "-m", "venv", os.path.join(script_dir, ".venv")], check=True)
            _log("Upgrading pip...")
            subprocess.run([venv_py, "-m", "pip", "install", "--upgrade", "pip", "--quiet", "--disable-pip-version-check"], timeout=120)
        except Exception as e:
            _log(f"Failed to create .venv with {sys.executable}: {e}")
            _log("Trying pip install into current Python instead...")
            venv_py = None
            venv_pip = None
    pip_targets = []
    if venv_pip and os.path.isfile(venv_pip):
        pip_targets.append((venv_pip, venv_py))
    pip_targets.append((f"{sys.executable} -m pip", sys.executable))
    for pip_cmd, py_exe in pip_targets:
        _log(f"Installing faster-whisper stack via {pip_cmd} ...")
        _status("Installing dependencies (1-2 min, first run only)...")
        try:
            if " -m pip" in pip_cmd:
                cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "faster-whisper", "soundfile", "av", "numpy", "customtkinter", "--quiet", "--disable-pip-version-check"]
            else:
                cmd = [venv_pip, "install", "--upgrade", "faster-whisper", "soundfile", "av", "numpy", "customtkinter", "--quiet", "--disable-pip-version-check"]
            subprocess.run(cmd, check=True, timeout=300)
            _log("Dependencies installed.")
            if py_exe == sys.executable:
                try:
                    import importlib
                    importlib.invalidate_caches()
                    import faster_whisper  # noqa: F401
                    return True
                except Exception as e:
                    _log(f"Installed but still cannot import in current Python: {e}")
                    _log("Restart the GUI to pick up new packages, or run Transcribe_WAVs.bat.")
                    return False
            else:
                _log("Installed into .venv — restart GUI or run Transcribe_WAVs.bat to use venv Python, or wait for pip install into current Python.")
                continue
        except Exception as e:
            _log(f"pip install failed with {pip_cmd}: {e}")
            continue
    _log("Could not install dependencies automatically. Try manually:")
    _log("  .venv\\Scripts\\pip install faster-whisper soundfile av numpy customtkinter")
    _log("or: python -m pip install faster-whisper soundfile av numpy customtkinter")
    return False


# ---------------------------------------------------------------------------
# GUI — Clickable dark shell
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Portable WAV/Media Transcriber")
        self.geometry("700x540")
        self.minsize(620, 440)
        self.configure(fg_color=Theme.BG_DARKEST)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self.folder_var = tk.StringVar(value="")
        self.vtt_var = tk.BooleanVar(value=False)
        self.model_var = tk.StringVar(value="large-v3")
        self.track_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.counter_var = tk.StringVar(value="")
        self._track_choices: list[tuple[str, int | None]] = [("Auto — container default", None)]
        self._track_source = ""
        self._track_selected = False
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.msg_queue: queue.Queue = queue.Queue()
        self.total = 0

        self._build_ui()
        self._poll_queue()

        try:
            if any(f.lower().endswith(MEDIA_EXTS) for f in os.listdir(SCRIPT_DIR)):
                self.folder_var.set(SCRIPT_DIR)
                self._on_folder_change()
        except Exception:
            pass
        if not ENGINE_AVAILABLE:
            self._log(f"Engine import failed: {ENGINE_ERROR}")
            self._log("Click Transcribe to auto-install dependencies, or run Transcribe_WAVs.bat once.")

    # -- layout -------------------------------------------------------------

    def _build_ui(self):
        self._create_header()
        self._create_controls()
        self._create_main()
        self._create_footer()

    def _create_header(self):
        header = ctk.CTkFrame(self, fg_color=Theme.BG_SURFACE, corner_radius=12)
        header.grid(row=0, column=0, padx=14, pady=(14, 6), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Portable WAV/Media Transcriber",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_BRIGHT,
            anchor="w",
        ).grid(row=0, column=0, padx=(14, 8), pady=10, sticky="w")

        self.status_dot = ctk.CTkLabel(
            header,
            text="\u25CF Idle",
            font=Theme.FONT_SMALL,
            text_color=Theme.GREY,
        )
        self.status_dot.grid(row=0, column=1, padx=(0, 14), pady=10, sticky="e")

    def _create_controls(self):
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=1, column=0, padx=14, pady=(0, 4), sticky="ew")
        controls.grid_columnconfigure(0, weight=1)

        # Row A — folder
        row_a = ctk.CTkFrame(controls, fg_color="transparent")
        row_a.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        row_a.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row_a, text="Folder", font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_DIM, anchor="w",
        ).grid(row=0, column=0, padx=(0, 6), pady=3, sticky="w")

        self.entry = ctk.CTkEntry(
            row_a,
            textvariable=self.folder_var,
            placeholder_text="Paste folder path or click Browse…",
            font=Theme.FONT_BODY,
            height=28,
            fg_color=Theme.BG_ENTRY,
            border_color=Theme.DIVIDER,
            text_color=Theme.TEXT_BRIGHT,
        )
        self.entry.grid(row=0, column=1, sticky="ew", pady=3)
        self.entry.bind("<KeyRelease>", lambda e: self._on_folder_change())
        self.entry.bind("<FocusOut>", lambda e: self._on_folder_change())

        self.browse_btn = ctk.CTkButton(
            row_a, text="Browse", width=72, height=28,
            font=Theme.FONT_BUTTON,
            fg_color=Theme.BLUE, hover_color=Theme.BLUE_HOVER,
            command=self._browse,
        )
        self.browse_btn.grid(row=0, column=2, padx=(6, 0), pady=3)

        # Row B — model / VTT / track
        row_b = ctk.CTkFrame(controls, fg_color="transparent")
        row_b.grid(row=1, column=0, sticky="ew")
        # let track menu expand
        row_b.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(
            row_b, text="Model", font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_DIM, anchor="w",
        ).grid(row=0, column=0, padx=(0, 6), pady=3, sticky="w")

        self.model_large_rb = ctk.CTkRadioButton(
            row_b, text="Large-v3 (best)", variable=self.model_var, value="large-v3",
            font=Theme.FONT_BODY, text_color=Theme.TEXT_BRIGHT,
            fg_color=Theme.BLUE, hover_color=Theme.BLUE_HOVER,
            border_color=Theme.GREY, border_width_checked=6,
            radiobutton_width=16, radiobutton_height=16,
        )
        self.model_large_rb.grid(row=0, column=1, padx=(0, 8), pady=3)

        self.model_turbo_rb = ctk.CTkRadioButton(
            row_b, text="Turbo (fast)", variable=self.model_var, value="turbo",
            font=Theme.FONT_BODY, text_color=Theme.TEXT_BRIGHT,
            fg_color=Theme.BLUE, hover_color=Theme.BLUE_HOVER,
            border_color=Theme.GREY, border_width_checked=6,
            radiobutton_width=16, radiobutton_height=16,
        )
        self.model_turbo_rb.grid(row=0, column=2, padx=(0, 12), pady=3)

        self.vtt_cb = ctk.CTkCheckBox(
            row_b, text="Also write .vtt", variable=self.vtt_var,
            font=Theme.FONT_BODY, text_color=Theme.TEXT_BRIGHT,
            fg_color=Theme.BLUE, hover_color=Theme.BLUE_HOVER,
            border_color=Theme.GREY, checkbox_width=16, checkbox_height=16,
            corner_radius=4,
        )
        self.vtt_cb.grid(row=0, column=3, padx=(0, 12), pady=3)

        ctk.CTkLabel(
            row_b, text="Audio track (videos):", font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_DIM, anchor="w",
        ).grid(row=0, column=4, padx=(0, 6), pady=3, sticky="w")

        self.track_combo = ctk.CTkOptionMenu(
            row_b,
            variable=self.track_var,
            values=[c[0] for c in self._track_choices],
            font=Theme.FONT_BODY,
            height=28, width=220,
            fg_color=Theme.BTN_SURFACE,
            button_color=Theme.BTN_SURFACE_HOVER,
            button_hover_color=Theme.GREY,
            text_color=Theme.TEXT_BRIGHT,
            dropdown_fg_color=Theme.BG_SURFACE,
            dropdown_hover_color=Theme.BTN_SURFACE_HOVER,
            command=self._on_track_pick,
        )
        self.track_combo.set(self._track_choices[0][0])
        self.track_combo.grid(row=0, column=5, pady=3, sticky="ew")

    def _create_main(self):
        self.main_frame = ctk.CTkFrame(self, fg_color=Theme.BG_SURFACE, corner_radius=12)
        self.main_frame.grid(row=2, column=0, padx=14, pady=6, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(3, weight=1)

        # Toolbar — Transcribe / Open folder / status on right
        toolbar = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        toolbar.grid(row=0, column=0, padx=10, pady=(8, 6), sticky="ew")
        toolbar.grid_columnconfigure(2, weight=1)

        self.transcribe_btn = ctk.CTkButton(
            toolbar, text="Transcribe", width=140, height=28,
            font=Theme.FONT_BUTTON,
            fg_color=Theme.CRIMSON, hover_color=Theme.CRIMSON_HOVER,
            command=self._on_transcribe,
        )
        self.transcribe_btn.grid(row=0, column=0, padx=(0, 6), sticky="w")

        self.open_btn = ctk.CTkButton(
            toolbar, text="Open folder", width=102, height=28,
            font=Theme.FONT_BUTTON,
            fg_color=Theme.BTN_SURFACE, hover_color=Theme.BTN_SURFACE_HOVER,
            text_color=Theme.TEXT_BRIGHT,
            command=self._open_folder, state="disabled",
        )
        self.open_btn.grid(row=0, column=1, padx=(0, 8), sticky="w")

        self.toolbar_status = ctk.CTkLabel(
            toolbar, textvariable=self.status_var,
            font=Theme.FONT_SMALL, text_color=Theme.TEXT_DIM,
            anchor="w", wraplength=280, justify="left",
        )
        self.toolbar_status.grid(row=0, column=2, padx=(6, 0), sticky="ew")

        # Progress + counter (separate rows so they don't overlap)
        self.progress = ctk.CTkProgressBar(
            self.main_frame, height=10, corner_radius=6,
            fg_color=Theme.BG_ENTRY, progress_color=Theme.CRIMSON,
        )
        self.progress.grid(row=1, column=0, padx=10, pady=(0, 2), sticky="ew")
        self.progress.set(0)

        self.counter_label = ctk.CTkLabel(
            self.main_frame, textvariable=self.counter_var,
            font=Theme.FONT_SMALL, text_color=Theme.TEXT_DIM,
            anchor="w",
        )
        self.counter_label.grid(row=2, column=0, padx=10, pady=(0, 2), sticky="w")

        # Log — CTkTextbox with dark styling
        self.log = ctk.CTkTextbox(
            self.main_frame,
            fg_color=Theme.BG_ENTRY,
            corner_radius=8,
            font=("Consolas", 10),
            text_color=Theme.TEXT_DIM,
            wrap="word",
            border_width=0,
        )
        self.log.grid(row=3, column=0, padx=10, pady=(4, 10), sticky="nsew")
        # CTkTextbox starts editable; disable after init
        self.log.configure(state="disabled")

    def _create_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, padx=16, pady=(0, 14), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.footer_label = ctk.CTkLabel(
            footer,
            text="Paste a folder, choose model/track, then click Transcribe.",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_DIM,
            anchor="w",
        )
        self.footer_label.grid(row=0, column=0, sticky="ew")

    # -- track helpers ------------------------------------------------------

    def _on_track_pick(self, _value=None):
        self._track_selected = True

    def _current_track_ordinal(self):
        label = self.track_var.get()
        for lbl, ordinal in getattr(self, "_track_choices", []):
            if lbl == label:
                return ordinal
        return None

    def _inspect_tracks(self, folder: str):
        try:
            vids = sorted(
                f for f in os.listdir(folder)
                if f.lower().endswith(VIDEO_EXTS) and os.path.isfile(os.path.join(folder, f))
            )
        except Exception:
            vids = []
        choices: list[tuple[str, int | None]] = [("Auto — container default", None)]
        self._track_source = ""
        if vids:
            streams = []
            try:
                import transcribe_wav as _tw
                streams = _tw.probe_audio_streams(os.path.join(folder, vids[0])) or []
            except Exception:
                streams = []
            if streams:
                self._track_source = vids[0]
                for s in streams:
                    i = s["index"]
                    parts = [s.get("codec") or "audio"]
                    ch = s.get("channels") or 0
                    if ch == 1:
                        parts.append("mono")
                    elif ch > 1:
                        parts.append(f"{ch}ch")
                    if s.get("language"):
                        parts.append(f"[{s['language']}]")
                    if s.get("title"):
                        parts.append(s["title"])
                    desc = " — ".join(p for p in parts if p)
                    choices.append((f"Stream {i} (Track {i + 1}) — {desc}", i))
            else:
                for i in range(DEFAULT_TRACK_ORDINAL + 1):
                    choices.append((f"Stream {i} (Track {i + 1})", i))
        self._track_choices = choices
        ordinals = [c[1] for c in choices]
        labels = [c[0] for c in choices]
        self.track_combo.configure(values=labels)
        if self._track_selected:
            pick = self._current_track_ordinal()
            if pick not in ordinals:
                pick = DEFAULT_TRACK_ORDINAL if DEFAULT_TRACK_ORDINAL in ordinals else None
        else:
            pick = DEFAULT_TRACK_ORDINAL if DEFAULT_TRACK_ORDINAL in ordinals else None
        new_label = labels[ordinals.index(pick)] if pick is not None else labels[0]
        self.track_var.set(new_label)
        # keep displayed value in sync (OptionMenu needs explicit set)
        try:
            self.track_combo.set(new_label)
        except Exception:
            pass

    # -- UI helpers ---------------------------------------------------------

    def _log(self, msg: str):
        # Smart-follow: capture whether view is at bottom before insert
        try:
            near_bottom = self.log.yview()[1] >= 0.98  # type: ignore[attr-defined]
        except Exception:
            near_bottom = True
        self.log.configure(state="normal")
        self.log.insert("end", msg.rstrip() + "\n")
        if near_bottom:
            try:
                self.log.see("end")
            except Exception:
                pass
        self.log.configure(state="disabled")

    def _set_status(self, msg: str):
        self.status_var.set(msg)
        # Footer mirrors toolbar status for long messages (elided toolbar keeps short)
        try:
            self.footer_label.configure(text=msg if msg else "Paste a folder, choose model/track, then click Transcribe.")
        except Exception:
            pass
        # Header dot coloring
        dot_text, dot_color = self._dot_for_status(msg)
        try:
            self.status_dot.configure(text=dot_text, text_color=dot_color)
        except Exception:
            pass

    def _dot_for_status(self, msg: str) -> tuple[str, str]:
        low = (msg or "").lower()
        if any(k in low for k in ("transcribing", "loading model", "downloading", "extracting", "preparing", "checking ffmpeg", "installing")):
            return "\u25CF Working", Theme.AMBER
        if "done" in low or "finished" in low:
            # distinguish error-filled finished
            if "failed" in low and "0 failed" not in low:
                return "\u25CF Done", Theme.AMBER
            return "\u25CF Done", Theme.GREEN
        if any(k in low for k in ("failed", "error", "not found", "no supported")):
            return "\u25CF Error", Theme.RED
        if "cancel" in low:
            return "\u25CF Cancelled", Theme.AMBER
        if "found" in low and "media" in low:
            return "\u25CF Ready", Theme.GREEN
        if not msg:
            return "\u25CF Idle", Theme.GREY
        return "\u25CF Idle", Theme.TEXT_DIM

    def _set_progress(self, done: int, total: int):
        if total <= 0:
            self.progress.set(0)
        else:
            self.progress.set(max(0.0, min(1.0, done / total)))
        self.counter_var.set(f"{done} / {total}" if total else "")

    def _on_folder_change(self, *_):
        path = normalize_folder(self.folder_var.get())
        if not path:
            self._set_status("")
            self.counter_var.set("")
            self._set_progress(0, 0)
            return
        if not os.path.isdir(path):
            self._set_status("Folder not found")
            self.counter_var.set("")
            self._set_progress(0, 0)
            return
        try:
            media = [f for f in os.listdir(path) if f.lower().endswith(MEDIA_EXTS)]
        except Exception as e:
            self._set_status(f"Cannot list folder: {e}")
            return
        n = len(media)
        if n == 0:
            self._set_status("No supported media files in this folder")
            self.counter_var.set("")
            self._set_progress(0, 0)
            return
        self._inspect_tracks(path)
        status = f"Found {n} media file(s)"
        if self._track_source:
            status += f" — tracks from {self._track_source}"
        self._set_status(status)
        self.counter_var.set("")
        self._set_progress(0, n)
        # enable Open folder when path valid
        try:
            self.open_btn.configure(state="normal")
        except Exception:
            pass

    def _browse(self):
        initial = normalize_folder(self.folder_var.get())
        if not initial or not os.path.isdir(initial):
            initial = SCRIPT_DIR
        chosen = filedialog.askdirectory(parent=self, initialdir=initial, title="Choose folder with media files")
        if chosen:
            self.folder_var.set(chosen)
            self._on_folder_change()

    def _open_folder(self):
        path = normalize_folder(self.folder_var.get())
        if path and os.path.isdir(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
            except Exception:
                subprocess.Popen(f'explorer "{path}"')

    def _on_transcribe(self):
        if self.worker and self.worker.is_alive():
            self.cancel_event.set()
            self._set_status("Cancelling after current file...")
            try:
                self.transcribe_btn.configure(state="disabled")
            except Exception:
                pass
            return

        folder = normalize_folder(self.folder_var.get())
        if not folder:
            messagebox.showwarning("No folder", "Paste or browse to a folder containing media files first.", parent=self)
            return
        if not os.path.isdir(folder):
            messagebox.showerror("Folder not found", f"Not a directory:\n{folder}", parent=self)
            return

        ok, msg = check_bootstrap(SCRIPT_DIR)
        if not ok:
            if getattr(sys, 'frozen', False):
                messagebox.showinfo("Setup needed", msg, parent=self)
                self._log(msg)
                return
            else:
                if not messagebox.askyesno("Setup needed",
                    msg + "\n\nClick Yes to auto-install now (needs internet), or No to cancel and run Transcribe_WAVs.bat manually.",
                    parent=self):
                    self._log(msg)
                    return

        try:
            files = sorted(
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith(MEDIA_EXTS)
                and os.path.isfile(os.path.join(folder, f))
            )
        except Exception as e:
            messagebox.showerror("Error", f"Cannot list folder:\n{e}", parent=self)
            return
        if not files:
            messagebox.showinfo("No files", "No supported media files found in that folder (top level only).", parent=self)
            return

        self.total = len(files)
        self._set_progress(0, self.total)
        self._set_status("Preparing...")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._log(f"Found {self.total} media file(s) in {folder}")
        self._log(f"App dir: {SCRIPT_DIR} ({'frozen exe' if getattr(sys, 'frozen', False) else 'source'})")
        model_choice = self.model_var.get()
        track_label = self.track_var.get() or "Auto"
        track_note = "container default" if self._current_track_ordinal() is None else f"{track_label}"
        self._log(f"Model: {model_choice} | Audio track: {track_note}")
        if self.vtt_var.get():
            self._log("VTT output enabled — will write .vtt beside each .txt")
        try:
            self.transcribe_btn.configure(text="Cancel", fg_color=Theme.GREY, hover_color=Theme.GREY_HOVER, state="normal")
            self.open_btn.configure(state="disabled")
        except Exception:
            pass
        self.cancel_event.clear()

        write_vtt_flag = bool(self.vtt_var.get())
        self.worker = threading.Thread(
            target=self._run_job,
            args=(files, write_vtt_flag, self.model_var.get(), self._current_track_ordinal()),
            daemon=True,
        )
        self.worker.start()

    # -- Worker (background thread) -----------------------------------------

    def _run_job(self, files, write_vtt_flag: bool, model_name: str = "large-v3", stream_ordinal=None):
        q = self.msg_queue
        def qlog(m): q.put(("log", str(m)))
        def qstatus(m): q.put(("status", str(m)))
        try:
            if not getattr(sys, 'frozen', False) and not ENGINE_AVAILABLE:
                qstatus("Installing dependencies...")
                if not ensure_source_deps(SCRIPT_DIR, log_fn=qlog, status_fn=qstatus):
                    qlog("ERROR: dependencies not ready. Restart GUI after install or run Transcribe_WAVs.bat")
                    q.put(("done", (0, 0, len(files))))
                    return
                try:
                    import importlib
                    import transcribe_wav as _tw  # noqa: F401
                    globals()["transcribe_wav"] = _tw
                    importlib.invalidate_caches()
                except Exception as e:
                    qlog(f"ERROR: still cannot import engine after install: {e}")
                    q.put(("done", (0, 0, len(files))))
                    return

            import transcribe_wav
            tools_dir = os.path.join(SCRIPT_DIR, ".tools")
            if os.path.isdir(tools_dir) and tools_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = tools_dir + os.pathsep + os.environ.get("PATH", "")

            # Partition before loading the model: skip names must track the
            # engine's write names (incl. _sN suffix for non-default tracks),
            # and a folder with nothing to do skips the model load entirely.
            pending, skipped_pairs = transcribe_wav.filter_pending(files, stream_ordinal, force=False)
            for spath, found in skipped_pairs:
                q.put(("log", f"SKIPPED: {os.path.basename(spath)} — output exists ({os.path.basename(found)})"))
            if skipped_pairs:
                q.put(("progress", (len(skipped_pairs), "")))
            if not pending:
                q.put(("done", (0, len(skipped_pairs), 0)))
                return

            qstatus("Checking ffmpeg...")
            if not ensure_ffmpeg(SCRIPT_DIR, log_fn=qlog, status_fn=qstatus):
                qlog("ERROR: ffmpeg setup failed. Put ffmpeg.exe into .tools manually or check internet.")
                qlog(f"Get it from {FFMPEG_URL}")
                q.put(("done", (0, len(skipped_pairs), 0)))
                return

            q.put(("status", f"Loading model ({model_name}, auto compute)..."))
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    model, compute_used = transcribe_wav.load_model(model_name, "auto")
                captured = buf.getvalue()
                if captured.strip():
                    for line in captured.strip().splitlines():
                        q.put(("log", line.rstrip()))
                q.put(("log", f"Model ready — {model_name} / {compute_used}"))
            except Exception as e:
                try:
                    captured = buf.getvalue()  # type: ignore
                    if captured.strip():
                        for line in captured.strip().splitlines():
                            q.put(("log", line))
                except Exception:
                    pass
                q.put(("log", f"ERROR loading model: {e}"))
                import traceback as _tb
                q.put(("log", _tb.format_exc().strip()))
                q.put(("done", (0, len(skipped_pairs), 0)))
                return

            success = 0
            failed = 0
            done_count = len(skipped_pairs)   # skips already advanced the bar above

            for wav_path in pending:
                if self.cancel_event.is_set():
                    q.put(("log", "Cancelled by user."))
                    break

                base = os.path.basename(wav_path)

                q.put(("status", f"Transcribing {base}..."))
                q.put(("progress_label", f"{done_count + 1} / {len(files)} — {base}"))
                q.put(("progress", (done_count, base)))

                buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                        ok = transcribe_wav.transcribe_file(
                            wav_path, model, compute_used,
                            prompt=transcribe_wav.DEFAULT_PROMPT,
                            user_prompt=None,
                            terms=None,
                            use_vad=True,
                            style_retry=True,
                            write_vtt_flag=write_vtt_flag,
                            stream_index=stream_ordinal,
                        )
                    captured = buf.getvalue()
                    if captured.strip():
                        for line in captured.strip().splitlines():
                            q.put(("log", line.rstrip()))
                    if ok:
                        q.put(("log", f"DONE: {base}"))
                        success += 1
                    else:
                        last_err = ""
                        if captured.strip():
                            for line in reversed(captured.strip().splitlines()):
                                if "ERROR" in line or "Traceback" in line or "Failed" in line:
                                    last_err = line.strip()
                                    break
                        if last_err:
                            q.put(("log", f"FAILED: {base} — {last_err}"))
                        else:
                            q.put(("log", f"FAILED: {base} — see log above"))
                        failed += 1
                except Exception as e:
                    captured = buf.getvalue()
                    if captured.strip():
                        for line in captured.strip().splitlines():
                            q.put(("log", line))
                    q.put(("log", f"FAILED: {base} — {e}"))
                    import traceback as _tb2
                    q.put(("log", _tb2.format_exc().strip()))
                    failed += 1

                done_count += 1
                q.put(("progress", (done_count, base)))

            q.put(("done", (success, len(skipped_pairs), failed)))

        except Exception as e:
            import traceback as _tb
            q.put(("log", f"Worker crashed: {e}"))
            q.put(("log", _tb.format_exc().strip()))
            q.put(("done", (0, 0, len(files) if 'files' in locals() else 0)))

    # -- Queue polling (main thread) ----------------------------------------

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._log(str(payload))
                elif kind == "status":
                    self._set_status(str(payload))
                elif kind == "progress":
                    done, _base = payload
                    self._set_progress(done, self.total)
                elif kind == "progress_label":
                    self.counter_var.set(str(payload))
                elif kind == "done":
                    success, skipped, failed = payload
                    total = self.total
                    done_val = success + skipped + failed
                    self._set_progress(done_val, total)
                    if self.cancel_event.is_set():
                        self._set_status(f"Cancelled — {success} transcribed, {skipped} skipped, {failed} failed")
                        self._log(f"Cancelled: {success} transcribed, {skipped} skipped, {failed} failed out of {total}")
                    else:
                        self._set_status(f"Finished: {success} transcribed, {skipped} skipped, {failed} failed")
                        self._log(f"Finished: {success} transcribed, {skipped} skipped, {failed} failed out of {total}")
                    try:
                        self.transcribe_btn.configure(text="Transcribe", fg_color=Theme.CRIMSON, hover_color=Theme.CRIMSON_HOVER, state="normal")
                        self.open_btn.configure(state="normal")
                    except Exception:
                        pass
                    self._on_folder_change()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
