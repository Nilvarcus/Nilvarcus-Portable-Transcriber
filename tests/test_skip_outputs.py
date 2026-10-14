"""Plain-assert tests for the skip-existing-output logic (no pytest needed).

Run:  .venv\\Scripts\\python.exe tests\\test_skip_outputs.py

Covers the shared helpers in transcribe_wav.py:
  output_paths()   - skip names must equal write names (incl. _sN suffix)
  existing_output()/filter_pending() - .txt OR .vtt counts as done;
  a different track's output never masks the selected track; --force bypasses.

Video cases monkeypatch probe_audio_streams, so no real containers or the
whisper model are needed.
"""
import os
import sys
import tempfile
import contextlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import transcribe_wav

FAKE_4_STREAMS = [
    {"index": i, "codec": "aac", "channels": 2, "language": "", "title": f"Track {i + 1}"}
    for i in range(4)
]
FAKE_2_STREAMS = FAKE_4_STREAMS[:2]


def _fake_probe(streams):
    def probe(_input_path):
        return streams
    return probe


@contextlib.contextmanager
def probed(streams):
    """Swap in a fake probe_audio_streams for the duration of the block."""
    saved = transcribe_wav.probe_audio_streams
    transcribe_wav.probe_audio_streams = _fake_probe(streams)
    try:
        yield
    finally:
        transcribe_wav.probe_audio_streams = saved


def main():
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "clip.wav")
        open(wav, "w").close()

        # 1. .wav + sibling .txt -> skipped, named path is the txt
        txt = os.path.join(d, "clip.txt")
        open(txt, "w").close()
        pending, skipped = transcribe_wav.filter_pending([wav], 3)
        assert pending == [] and skipped == [(wav, txt)], (pending, skipped)
        assert transcribe_wav.existing_output(wav, 3) == txt
        assert transcribe_wav.output_paths(wav, 3) == (txt, txt[:-4] + ".vtt")
        os.remove(txt)

        # 2. .wav + sibling .vtt only -> skipped (either extension counts)
        vtt = os.path.join(d, "clip.vtt")
        open(vtt, "w").close()
        pending, skipped = transcribe_wav.filter_pending([wav], 3)
        assert pending == [] and skipped == [(wav, vtt)], (pending, skipped)
        os.remove(vtt)

        # 3. 4-stream video, ordinal 3 -> write/skip name is suffixed video_s4
        vid = os.path.join(d, "video.mp4")
        open(vid, "w").close()
        s4txt = os.path.join(d, "video_s4.txt")
        s4vtt = os.path.join(d, "video_s4.vtt")
        open(s4txt, "w").close()
        with probed(FAKE_4_STREAMS):
            assert transcribe_wav.output_paths(vid, 3) == (s4txt, s4vtt)
            pending, skipped = transcribe_wav.filter_pending([vid], 3)
        assert pending == [] and skipped == [(vid, s4txt)], (pending, skipped)
        os.remove(s4txt)

        # 4. only another track's plain output exists -> NOT skipped (Track 4)
        plain = os.path.join(d, "video.txt")
        open(plain, "w").close()
        with probed(FAKE_4_STREAMS):
            pending, skipped = transcribe_wav.filter_pending([vid], 3)
        assert pending == [vid] and skipped == [], (pending, skipped)

        # 4b. same with the selected track's own plain output (Auto runs) -> skip
        os.remove(plain)
        open(plain, "w").close()
        with probed(FAKE_4_STREAMS):
            pending, skipped = transcribe_wav.filter_pending([vid], -1)
        assert pending == [] and skipped == [(vid, plain)], (pending, skipped)
        os.remove(plain)

        # 5. no outputs anywhere -> pending
        with probed(FAKE_4_STREAMS):
            pending, skipped = transcribe_wav.filter_pending([wav, vid], 3)
        assert pending == [wav, vid] and skipped == [], (pending, skipped)

        # 6. force=True -> everything pending despite existing outputs
        open(s4txt, "w").close()
        open(txt, "w").close()
        with probed(FAKE_4_STREAMS):
            pending, skipped = transcribe_wav.filter_pending([wav, vid], 3, force=True)
        assert pending == [wav, vid] and skipped == [], (pending, skipped)
        os.remove(s4txt)
        os.remove(txt)

        # 7. out-of-range ordinal clamps: 2-stream video, ordinal 3 -> stream 1
        #    (Track 2) -> skip name video_s2 matches the write name
        vid2 = os.path.join(d, "video2.mp4")
        open(vid2, "w").close()
        s2txt = os.path.join(d, "video2_s2.txt")
        s2vtt = os.path.join(d, "video2_s2.vtt")
        open(s2txt, "w").close()
        with probed(FAKE_2_STREAMS):
            assert transcribe_wav.output_paths(vid2, 3) == (s2txt, s2vtt)
            pending, skipped = transcribe_wav.filter_pending([vid2], 3)
        assert pending == [] and skipped == [(vid2, s2txt)], (pending, skipped)

    print("All skip-logic tests passed.")


if __name__ == "__main__":
    main()