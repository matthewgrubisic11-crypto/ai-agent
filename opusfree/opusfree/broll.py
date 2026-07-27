"""Contextual B-roll: fetch free stock clips (Pexels) and overlay them.

Set PEXELS_API_KEY (free, no card: https://www.pexels.com/api/) in .env to
turn on real B-roll. Without a key, opusfree still emits the b-roll *queries*
as directives; it just won't fetch footage.

overlay_broll() composites downloaded clips full-frame over a base video for a
couple of seconds each (masking jump cuts / illustrating keywords), then fades
back to the speaker.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.parse
import urllib.request
from typing import List, Optional, Tuple


def have_pexels() -> bool:
    return bool(os.environ.get("PEXELS_API_KEY"))


def fetch_broll(query: str, out_dir: str, min_dur: float = 3.0
                ) -> Optional[str]:
    """Download one portrait-ish stock clip for ``query``. Returns path or None."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    try:
        url = ("https://api.pexels.com/videos/search?per_page=3&orientation="
               "portrait&query=" + urllib.parse.quote(query))
        req = urllib.request.Request(url, headers={"Authorization": key})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        videos = data.get("videos") or []
        if not videos:
            return None
        # pick a mid-resolution mp4 file
        files = sorted(videos[0].get("video_files", []),
                       key=lambda f: (f.get("height") or 0))
        pick = None
        for f in files:
            if (f.get("height") or 0) >= 720 and f.get("link"):
                pick = f["link"]
                break
        pick = pick or (files[-1]["link"] if files else None)
        if not pick:
            return None
        safe = "".join(c for c in query if c.isalnum())[:20] or "broll"
        path = os.path.join(out_dir, f"broll_{safe}.mp4")
        with urllib.request.urlopen(pick, timeout=60) as r, open(path, "wb") as fh:
            fh.write(r.read())
        return path
    except Exception as exc:  # pragma: no cover - network
        print(f"  [broll] fetch failed for {query!r}: {exc}")
        return None


def overlay_broll(base_video: str, out_video: str,
                  clips: List[Tuple[float, float, str]],
                  out_w: int = 1080, out_h: int = 1920) -> bool:
    """Overlay b-roll clips onto base_video.

    ``clips`` = [(start_sec, dur_sec, path), ...] in the OUTPUT timeline.
    Each b-roll is scaled to cover the frame and shown for its window, with a
    quick crossfade in/out. Returns True on success.
    """
    clips = [(s, d, p) for (s, d, p) in clips if p and os.path.exists(p)][:6]
    if not clips:
        return False

    inputs = ["-i", os.path.abspath(base_video)]
    parts, last = [], "[0:v]"
    for i, (start, dur, path) in enumerate(clips, start=1):
        inputs += ["-i", os.path.abspath(path)]
        # scale/crop b-roll to cover, trim to window, fade edges
        parts.append(
            f"[{i}:v]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},trim=0:{dur:.2f},setpts=PTS-STARTPTS,"
            f"fade=t=in:st=0:d=0.2,fade=t=out:st={max(dur-0.2,0):.2f}:d=0.2[b{i}]")
        parts.append(
            f"{last}[b{i}]overlay=0:0:enable='between(t,{start:.2f},"
            f"{start + dur:.2f})'[v{i}]")
        last = f"[v{i}]"

    fc = ";".join(parts)
    cmd = (["ffmpeg", "-y"] + inputs +
           ["-filter_complex", fc, "-map", last, "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-c:a", "copy", "-movflags", "+faststart",
            os.path.abspath(out_video)])
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        print(f"  [broll] overlay failed: {exc.stderr[-400:] if exc.stderr else exc}")
        return False
