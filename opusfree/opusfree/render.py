"""Probe source video and render a final clip with ffmpeg.

Pipeline per clip: trim -> crop to speaker -> scale/pad to 1080x1920 ->
burn in the ASS captions -> encode MP4 (H.264 + AAC). Requires the ffmpeg and
ffprobe binaries on PATH (https://ffmpeg.org/download.html).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile


def ensure_ffmpeg() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise RuntimeError(
                f"'{binary}' not found on PATH. Install ffmpeg: "
                "https://ffmpeg.org/download.html"
            )


def probe_dimensions(video_path: str) -> tuple[int, int]:
    """Return (width, height) of the first video stream."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", video_path],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(out.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def render_clip(video_path: str, out_path: str, start: float, end: float,
                crop: tuple[int, int, int, int], ass_text: str,
                out_w: int = 1080, out_h: int = 1920) -> None:
    """Render one vertical, captioned clip to ``out_path``."""
    cw, ch, cx, cy = crop
    duration = max(end - start, 0.1)

    # ASS must live in a file. Rather than embed its absolute path in the
    # filtergraph (which needs fragile per-OS escaping of ':' and '\' and
    # breaks on newer ffmpeg), we run ffmpeg *from* the caption folder and
    # reference the file by bare name -- no special chars, works everywhere.
    tmp_dir = tempfile.mkdtemp(prefix="opusfree_")
    ass_name = "captions.ass"
    with open(os.path.join(tmp_dir, ass_name), "w", encoding="utf-8") as fh:
        fh.write(ass_text)

    # Input/output must be absolute since we change the working directory.
    video_abs = os.path.abspath(video_path)
    out_abs = os.path.abspath(out_path)

    vf = (
        f"crop={cw}:{ch}:{cx}:{cy},"
        f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},"
        f"subtitles={ass_name}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}", "-i", video_abs, "-t", f"{duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        out_abs,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=tmp_dir)
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise RuntimeError(f"ffmpeg failed:\n{exc.stderr[-1500:]}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
