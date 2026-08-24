"""
Portable WAV/Media Transcriber - fork of whisper-transcriber
Faster-whisper (large-v3 / turbo), Silero VAD, style-anchor, hallucination filters.
Handles audio files directly and video containers (.mp4/.mov/.mkv/.webm) by
extracting a selectable audio track via ffmpeg (-map 0:a:N).
Writes one .txt per input beside the source file (suffixed _sN when a
non-default track of a multi-track container is transcribed). No .vtt by default.
Forked from C:\\Users\\Nilva\\.agents\\skills\\whisper-transcriber\\scripts\\transcribe.py
"""
import os
import sys
import argparse
import tempfile
import subprocess
import io
import numpy as np

# Windowed PyInstaller exe (console=False) has sys.stdout == None — plain print() would crash.
# Provide a dummy so the engine can be imported/called from the GUI without a console.
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

MODEL_NAME       = "large-v3"
COMPUTE_TYPE     = "float16"
FALLBACK_COMPUTE = "int8_float16"
LANGUAGE         = "en"
AUDIO_EXTS       = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac")
VIDEO_EXTS       = (".mp4", ".mov", ".mkv", ".webm")
MEDIA_EXTS       = AUDIO_EXTS + VIDEO_EXTS
DEFAULT_STREAM   = 3   # 0-based audio ordinal; 3 = "Track 4" (DaVinci VO workflow)
TARGET_SR        = 16000
DEFAULT_PROMPT   = ("First impressions gameplay commentary. "
                    "This is a scripted voiceover with full sentences, "
                    "proper capitalization, and punctuation.")

# ---- audio extraction (compressed audio & video containers; .wav goes direct) ----
def extract_audio_ffmpeg(input_path, out_path, duration=None, stream_index=None):
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if stream_index is not None:
        cmd += ["-map", f"0:a:{stream_index}"]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-vn", "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(TARGET_SR), out_path]
    subprocess.run(cmd, capture_output=True, text=True)
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000

def probe_audio_streams(input_path):
    """
    Enumerate audio streams of a container using PyAV (already a dependency,
    no ffprobe parsing needed). Returns a list of dicts:
      {"index": ordinal, "codec": str, "channels": int, "language": str, "title": str}
    Empty list if the file cannot be opened/probed.
    """
    try:
        import av
        container = av.open(input_path)
        streams = []
        for i, s in enumerate(container.streams.audio):
            codec, channels = "audio", 0
            try:
                if s.codec_context:
                    codec = s.codec_context.name or codec
                    channels = s.codec_context.channels or 0
            except Exception:
                pass
            language, title = "", ""
            for md in (getattr(s, "tags", None) or {}, getattr(s, "metadata", None) or {}):
                try:
                    language = language or str(md.get("language") or "")
                    title = title or str(md.get("title") or "")
                except Exception:
                    pass
            streams.append({"index": i, "codec": codec, "channels": channels,
                            "language": language.strip(), "title": title.strip()})
        container.close()
        return streams
    except Exception:
        return []

def describe_stream(info):
    parts = [info.get("codec") or "audio"]
    ch = info.get("channels") or 0
    if ch == 1:
        parts.append("mono")
    elif ch > 1:
        parts.append(f"{ch}ch")
    if info.get("language"):
        parts.append(f"[{info['language']}]")
    if info.get("title"):
        parts.append(f"'{info['title']}'")
    return " ".join(parts)

def resolve_track(input_path, stream_index):
    """
    Resolve which audio stream to extract and what the output base name is.
    Returns (streams, effective_index, output_base):
      streams          probe_audio_streams() result ([] for .wav or probe failure)
      effective_index  ordinal passed to ffmpeg as -map 0:a:N (None = container default)
      output_base      path without extension; suffixed _sN when a non-default track
                       of a multi-stream container was requested (prevents .txt collisions)
    """
    base = os.path.splitext(input_path)[0]
    if input_path.lower().endswith(".wav"):
        return [], None, base
    streams = probe_audio_streams(input_path)
    n = len(streams)
    eff = stream_index
    if eff is not None:
        if eff < 0:
            eff = None
        elif n > 0 and eff >= n:
            print(f"  NOTE: requested stream {eff} but file has {n} audio stream(s) - using stream {n-1} (Track {n})")
            eff = n - 1
    out_base = base
    if n > 1 and eff not in (None, 0):
        out_base = f"{base}_s{eff + 1}"
    return streams, eff, out_base

def get_duration(path):
    try:
        import av
        container = av.open(path)
        duration = float(container.duration) / av.time_base if container.duration else 0
        if duration <= 0:
            for s in container.streams.audio:
                if s.duration:
                    duration = float(s.duration * s.time_base)
                    break
        container.close()
        return duration
    except Exception:
        return 0

_HALLUCINATION_PATTERNS = {
    "thank you", "thank you.", "thanks.", "thank you so much.",
    "thanks for watching.", "thanks for watching!",
    "thank you for watching.", "thank you for watching!",
    "please subscribe.", "subscribe.",
    "like and subscribe.", "like and subscribe!",
    "see you next time.", "see you in the next video.",
    "bye.", "bye bye.", "goodbye.",
    "you", "you.", "...", "",
}

def filter_hallucinations(segments):
    filtered = []
    for seg in segments:
        text = seg["text"].strip().lower()
        if text in _HALLUCINATION_PATTERNS:
            continue
        words = text.split()
        if len(words) >= 3 and len(set(words)) == 1:
            continue
        filtered.append(seg)
    return filtered

def filter_repeat_loops(segments, threshold=2):
    if not segments:
        return segments
    cleaned = [segments[0]]
    prev_texts = [segments[0]["text"].strip().lower()]
    for seg in segments[1:]:
        text = seg["text"].strip().lower()
        duration = seg["end"] - seg["start"]
        if len(prev_texts) >= threshold:
            recent = prev_texts[-threshold:]
            if all(p == text for p in recent):
                continue
        if prev_texts and duration < 1.0 and text == prev_texts[-1]:
            continue
        cleaned.append(seg)
        prev_texts.append(text)
    return cleaned

def filter_fragments(segments, min_duration=0.5, min_words=2, logprob_cutoff=-1.0, no_speech_cutoff=0.6):
    kept = []
    for seg in segments:
        duration = seg["end"] - seg["start"]
        word_count = len(seg["text"].strip().split())
        if duration < min_duration and word_count < min_words:
            low_conf = (seg.get("avg_logprob", 0) < logprob_cutoff or seg.get("no_speech_prob", 0) > no_speech_cutoff)
            if low_conf:
                continue
        kept.append(seg)
    return kept

def _style_collapsed(segments, min_words=100):
    text = " ".join(s["text"] for s in segments).strip()
    words = text.split()
    if len(words) < min_words:
        return False
    sentence_punct = sum(text.count(p) for p in (".", "?", "!"))
    punct_ratio = sentence_punct / len(words)
    lowercase_starts = sum(1 for s in segments if s["text"].strip()[:1].islower())
    lowercase_ratio = lowercase_starts / max(1, len(segments))
    return punct_ratio < 0.005 and lowercase_ratio > 0.8

def _looks_like_keyword_list(prompt):
    if any(p in prompt for p in ".!?"):
        return False
    return "," in prompt

def _collect_segments(segments_gen):
    return [{"start": seg.start, "end": seg.end, "text": seg.text,
             "avg_logprob": seg.avg_logprob, "no_speech_prob": seg.no_speech_prob} for seg in segments_gen]

def write_txt(segments, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(seg["text"].strip() + "\n")

def _format_vtt_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    # handle rounding overflow (e.g. 59.9995 -> 60.000)
    if millis == 1000:
        millis = 0
        secs += 1
        if secs == 60:
            secs = 0
            minutes += 1
            if minutes == 60:
                minutes = 0
                hours += 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

def write_vtt(segments, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for seg in segments:
            text = seg["text"].strip()
            if not text:
                continue
            start = _format_vtt_time(seg["start"])
            end = _format_vtt_time(seg["end"])
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")

def _is_oom(error):
    msg = str(error).lower()
    return "out of memory" in msg or ("cuda" in msg and "error" in msg)

def load_model(model_name, compute_type):
    from faster_whisper import WhisperModel
    if compute_type == "auto":
        for device, compute in [("cuda", "float16"), ("cuda", "int8_float16"), ("cpu", "int8")]:
            try:
                print(f"  Trying {device} {compute}...")
                m = WhisperModel(model_name, device=device, compute_type=compute)
                print(f"  Model: {model_name}  Device: {device.upper()}  Compute: {compute}")
                return m, compute
            except Exception as e:
                msg = str(e).lower()
                if "cuda" in msg or "out of memory" in msg or "cublas" in msg or "device" in msg:
                    print(f"  {device} {compute} not available: {e}")
                    continue
                raise
        raise RuntimeError("Failed to load model on any device")
    device = "cpu" if compute_type in ("int8", "float32") else "cuda"
    print(f"  Model: {model_name}  Device: {device.upper()}  Compute: {compute_type}")
    try:
        m = WhisperModel(model_name, device=device, compute_type=compute_type)
        return m, compute_type
    except Exception as e:
        if device == "cuda" and compute_type != FALLBACK_COMPUTE and _is_oom(e):
            print(f"  WARNING: GPU load failed: {e}")
            print(f"  Retrying with {FALLBACK_COMPUTE}...")
            m = WhisperModel(model_name, device=device, compute_type=FALLBACK_COMPUTE)
            return m, FALLBACK_COMPUTE
        raise

def _build_transcribe_kwargs(prompt, terms, use_vad):
    kwargs = dict(language=LANGUAGE, condition_on_previous_text=True, beam_size=5, best_of=5,
                  no_speech_threshold=0.6, log_prob_threshold=-0.7, compression_ratio_threshold=2.0, log_progress=True)
    if prompt:
        kwargs["initial_prompt"] = prompt
    if terms:
        kwargs["hotwords"] = terms
    if use_vad:
        kwargs["vad_filter"] = True
        kwargs["vad_parameters"] = dict(min_speech_duration_ms=250, min_silence_duration_ms=1000, speech_pad_ms=400)
    return kwargs

def transcribe_file(input_path, model, compute_used, prompt=None, user_prompt=None, terms=None, use_vad=True, style_retry=True, write_vtt_flag=False, stream_index=DEFAULT_STREAM):
    base_name = os.path.basename(input_path)
    dir_name = os.path.dirname(input_path) or "."
    is_wav = input_path.lower().endswith(".wav")
    streams, eff_stream, out_base_full = resolve_track(input_path, stream_index)
    output_name = os.path.basename(out_base_full)   # basename only; joined onto dir_name below
    if len(streams) > 1:
        chosen = streams[eff_stream] if eff_stream is not None else None
        if chosen:
            print(f"  Audio track: stream {eff_stream} (Track {eff_stream + 1}) of {len(streams)} - {describe_stream(chosen)}")
        else:
            print(f"  Audio track: container default of {len(streams)} streams")
    print(f"\n{'='*60}\n  Transcribing: {base_name}\n{'='*60}")
    dur = get_duration(input_path)
    if dur > 0:
        print(f"  Duration: {int(dur//60)}m {int(dur%60)}s")
    temp_path = None
    try:
        if is_wav:
            transcribe_path = input_path
        else:
            print("  Extracting audio via ffmpeg...")
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            temp_path = tmp.name
            tmp.close()
            extracted = extract_audio_ffmpeg(input_path, temp_path, stream_index=eff_stream)
            if not extracted and eff_stream is not None:
                print(f"  WARNING: could not map stream {eff_stream} - retrying with default audio track")
                extracted = extract_audio_ffmpeg(input_path, temp_path)
                if extracted:
                    # Name must reflect the track actually transcribed
                    output_name = os.path.splitext(base_name)[0]
            if not extracted:
                print("  ERROR: Failed to extract audio")
                return False
            transcribe_path = temp_path
        print(f"  Prompt: {prompt!r}")
        print(f"  Terms: {terms!r}" if terms else "  Terms: (none)")
        print(f"  VAD: {'on' if use_vad else 'off'}")
        print("  Transcribing...")
        kwargs = _build_transcribe_kwargs(prompt, terms, use_vad)
        segments_gen, info = model.transcribe(transcribe_path, **kwargs)
        segments = _collect_segments(segments_gen)
        if style_retry and _style_collapsed(segments):
            if prompt and prompt.startswith(DEFAULT_PROMPT):
                print("\n  WARNING: Style collapse detected despite anchor - keeping output.")
            else:
                retry_prompt = DEFAULT_PROMPT
                if user_prompt and not _looks_like_keyword_list(user_prompt):
                    retry_prompt = f"{DEFAULT_PROMPT} {user_prompt}"
                print(f"\n  WARNING: Style collapse, retrying with anchor: {retry_prompt!r}")
                kwargs = _build_transcribe_kwargs(retry_prompt, terms, use_vad)
                segments_gen, info = model.transcribe(transcribe_path, **kwargs)
                segments = _collect_segments(segments_gen)
                if _style_collapsed(segments):
                    print("  WARNING: Retry did not recover - keeping output.")
        if not segments:
            print("  ERROR: No segments produced.")
            return False
        segments = filter_hallucinations(segments)
        segments = filter_repeat_loops(segments)
        segments = filter_fragments(segments)
        if not segments:
            print("  WARNING: All segments filtered, writing empty txt")
            segments = []
        txt_path = os.path.join(dir_name, f"{output_name}.txt")
        write_txt(segments, txt_path)
        print(f"\n  DONE: {len(segments)} segments")
        print(f"  TXT: {txt_path}")
        if write_vtt_flag:
            vtt_path = os.path.join(dir_name, f"{output_name}.vtt")
            write_vtt(segments, vtt_path)
            print(f"  VTT: {vtt_path}")
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass

def main():
    parser = argparse.ArgumentParser(description="Portable WAV Transcriber (faster-whisper, audio-only)")
    parser.add_argument("path", nargs="?", default=".", help="File or directory to transcribe")
    parser.add_argument("--model", type=str, default=MODEL_NAME, help="Whisper model: large-v3, turbo, ... (default: large-v3)")
    parser.add_argument("--stream", type=int, default=DEFAULT_STREAM, help="Audio track ordinal for multi-track containers, 0-based (default: 3 = Track 4); -1 = container default")
    parser.add_argument("--compute", type=str, default="auto", help="Compute type: auto, float16, int8_float16, int8, float32 (default: auto)")
    parser.add_argument("--prompt", type=str, default=None, help="Extra prompt sentence appended to style anchor")
    parser.add_argument("--no-default-prompt", action="store_true", help="Disable built-in style anchor")
    parser.add_argument("--terms", type=str, default=None, help="Hotwords comma-separated")
    parser.add_argument("--no-vad", action="store_true", help="Disable Silero VAD")
    parser.add_argument("--no-style-retry", action="store_true", help="Disable style-collapse retry")
    parser.add_argument("--force", action="store_true", help="Overwrite existing .txt (batch skips by default)")
    parser.add_argument("--vtt", action="store_true", help="Also write .vtt subtitles beside each .txt")
    args = parser.parse_args()
    path = args.path
    if not os.path.exists(path):
        print(f"Path not found: {path}")
        sys.exit(1)
    if args.prompt and _looks_like_keyword_list(args.prompt):
        print("WARNING: --prompt looks like keyword list. Use --terms for glossaries.")
    if args.no_default_prompt:
        prompt = args.prompt
    elif args.prompt:
        prompt = f"{DEFAULT_PROMPT} {args.prompt}"
    else:
        prompt = DEFAULT_PROMPT
    print("Loading faster-whisper model...")
    model, compute_used = load_model(args.model, args.compute)
    files = []
    if os.path.isdir(path):
        for f in sorted(os.listdir(path)):
            if f.lower().endswith(MEDIA_EXTS):
                files.append(os.path.join(path, f))
    elif os.path.isfile(path):
        files.append(path)
    if not files:
        print("No media files found.")
        return
    print(f"Found {len(files)} file(s) to transcribe.")
    success = 0
    for p in files:
        _, _, out_base = resolve_track(p, args.stream)
        txt = out_base + ".txt"
        if os.path.exists(txt) and not args.force:
            print(f"SKIPPED (exists): {os.path.basename(p)}")
            success += 1
            continue
        if transcribe_file(p, model, compute_used, prompt=prompt, user_prompt=args.prompt, terms=args.terms, use_vad=not args.no_vad, style_retry=not args.no_style_retry, write_vtt_flag=args.vtt):
            success += 1
    print(f"\nFinished: {success}/{len(files)} files transcribed.")

if __name__ == "__main__":
    main()
