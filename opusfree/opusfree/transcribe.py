"""Speech-to-text with word-level timestamps, using faster-whisper (local)."""

from __future__ import annotations

import os

from .models import Segment, Transcript, Word


def transcribe(video_path: str, model_size: str = "base", language: str | None = None,
               compute_type: str = "int8", translate: bool = False) -> Transcript:
    """Transcribe a media file into a Transcript with word-level timings.

    Runs entirely on your machine via faster-whisper. ``model_size`` trades
    speed for accuracy: tiny/base (fast, CPU-friendly) up to large-v3 (best,
    wants a GPU). ``translate=True`` outputs English captions for any spoken
    language (Whisper's built-in translate task -- free).
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on env
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        ) from exc

    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)

    model = WhisperModel(model_size, device="auto", compute_type=compute_type)

    segments_iter, _info = model.transcribe(
        video_path,
        language=language,
        task="translate" if translate else "transcribe",
        word_timestamps=True,
        vad_filter=True,  # skip long silences -> tighter clips
    )

    transcript = Transcript()
    for seg in segments_iter:
        words = []
        for w in (seg.words or []):
            text = (w.word or "").strip()
            if not text:
                continue
            words.append(Word(text=text, start=float(w.start), end=float(w.end)))
        # Fall back to segment-level timing if a model returns no word data.
        if not words and (seg.text or "").strip():
            words = [Word(text=seg.text.strip(), start=float(seg.start),
                          end=float(seg.end))]
        if not words:
            continue
        transcript.segments.append(
            Segment(text=(seg.text or "").strip(), start=float(seg.start),
                    end=float(seg.end), words=words)
        )

    return transcript
