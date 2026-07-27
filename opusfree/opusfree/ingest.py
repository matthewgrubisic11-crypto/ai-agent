"""Source ingestion: accept a local file OR a link (YouTube, Vimeo, etc.).

Uses yt-dlp for links -- the same downloader the open-source Opus Clip clones
use. Returns a local file path the rest of the pipeline can read.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Callable, Optional


def is_url(source: str) -> bool:
    return source.strip().lower().startswith(("http://", "https://", "www."))


def fetch(source: str, out_dir: str,
          on_progress: Optional[Callable[[str], None]] = None) -> str:
    """Return a local video path for ``source`` (download it if it's a link)."""
    if not is_url(source):
        if not os.path.exists(source):
            raise FileNotFoundError(source)
        return source

    if shutil.which("yt-dlp") is None:
        raise RuntimeError(
            "yt-dlp is needed to download links. Install it: pip install yt-dlp")

    if on_progress:
        on_progress("Downloading video from link...")
    os.makedirs(out_dir, exist_ok=True)
    out_tmpl = os.path.join(out_dir, "_download.%(ext)s")
    # mp4 up to 1080p, single file, with audio.
    cmd = [
        "yt-dlp", "--no-playlist", "--force-overwrites",
        "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format", "mp4",
        "-o", out_tmpl, source.strip(),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Download failed:\n{(exc.stderr or '')[-800:]}") from exc

    for name in os.listdir(out_dir):
        if name.startswith("_download."):
            return os.path.join(out_dir, name)
    raise RuntimeError("Download produced no file.")
