# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Portable WAV Transcriber GUI
# Build with: .venv/Scripts/pyinstaller Transcribe_GUI.spec
# Output: dist/Transcribe_GUI.exe

import os
import faster_whisper
import customtkinter

# CRITICAL: Silero VAD model file must be bundled or vad_filter=True fails
# with FileNotFoundError inside the frozen exe (get_assets_path() looks in
# _MEIPASS/faster_whisper/assets). This was the cause of all-files-fail
# silently in earlier builds.
FW_ASSETS = os.path.join(os.path.dirname(faster_whisper.__file__), 'assets')
CTK_PATH = os.path.dirname(customtkinter.__file__)

block_cipher = None

a = Analysis(
    ['transcribe_gui.pyw'],
    pathex=[],
    binaries=[],
    datas=[
        # transcribe_wav.py is imported; PyInstaller traces it automatically,
        # but include explicitly for clarity when run as module.
        ('transcribe_wav.py', '.'),
        # Silero VAD onnx model used by faster-whisper's vad_filter=True
        (os.path.join(FW_ASSETS, 'silero_vad_v6.onnx'), os.path.join('faster_whisper', 'assets')),
        # CustomTkinter (dark theme shell matching Clickable Timestamp Recorder)
        (CTK_PATH, 'customtkinter'),
    ],
    hiddenimports=[
        'transcribe_wav',
        'faster_whisper',
        'av',
        'soundfile',
        'numpy',
        'customtkinter',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Transcribe_GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # set True if UPX is installed and you want smaller exe
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # no console window — GUI only (.pyw style)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
