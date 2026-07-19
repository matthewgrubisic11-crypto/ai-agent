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

    # ASS must live in a file; escape its path for ffmpeg's filtergraph.
    tmp_dir = tempfile.mkdtemp(prefix="opusfree_")
    ass_path = os.path.join(tmp_dir, "captions.ass")
    with open(ass_path, "w", encoding="utf-8") as fh:
        fh.write(ass_text)
    ass_escaped = ass_path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    vf = (
        f"crop={cw}:{ch}:{cx}:{cy},"
        f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},"
        f"subtitles='{ass_escaped}'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}", "-i", video_path, "-t", f"{duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise RuntimeError(f"ffmpeg failed:\n{exc.stderr[-1500:]}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
