"""Probe source video and render final clips with ffmpeg.

Per clip: trim -> reframe (single crop or two-speaker split-screen) ->
punch zooms on emphasis moments -> burn in ASS captions -> optional
synthesized riser/whoosh sound at the zoom moments -> encode MP4.

Requires ffmpeg + ffprobe on PATH (https://ffmpeg.org/download.html).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional


def ensure_ffmpeg() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise RuntimeError(
                f"'{binary}' not found on PATH. Install ffmpeg: "
                "https://ffmpeg.org/download.html"
            )


def probe_dimensions(video_path: str) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", video_path],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(out.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def _zoom_expr(zoom_times: List[float], fps: int = 30,
               strength: float = 0.08) -> str:
    """zoompan zoom expression: smooth pulse at each emphasis time.

    Gaussian-shaped pulses (~0.9s wide) written without commas so the
    expression needs no extra quoting inside the filtergraph.
    """
    pulses = "+".join(
        f"exp(-(on/{fps}-{t:.2f})*(on/{fps}-{t:.2f})/0.18)"
        for t in zoom_times
    )
    return f"1+{strength}*({pulses})"


def _make_whoosh(path: str, duration: float = 0.7) -> bool:
    """Synthesize a short rising 'anticipation' sweep with ffmpeg (no assets,
    no copyright). Returns True on success."""
    expr = "0.22*sin(2*PI*(180+1500*t*t)*t)*sin(PI*t/0.7)"
    cmd = ["ffmpeg", "-y", "-f", "lavfi",
           "-i", f"aevalsrc={expr}:d={duration}:s=44100",
           "-c:a", "pcm_s16le", path]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _build_video_chain(crop_spec: dict, out_w: int, out_h: int,
                       zoom_times: Optional[List[float]], ass_name: str,
                       with_captions: bool) -> str:
    """Build the filter_complex video chain from [0:v] to [vout]."""
    fps = 30
    if crop_spec["mode"] == "split":
        (w0, h0, x0, y0), (w1, h1, x1, y1) = crop_spec["crops"]
        half = out_h // 2
        chain = (
            f"[0:v]split=2[p0][p1];"
            f"[p0]crop={w0}:{h0}:{x0}:{y0},"
            f"scale={out_w}:{half}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{half}[top];"
            f"[p1]crop={w1}:{h1}:{x1}:{y1},"
            f"scale={out_w}:{out_h - half}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h - half}[bot];"
            f"[top][bot]vstack=inputs=2[reframed]"
        )
    else:
        cw, ch, cx, cy = crop_spec["crop"]
        chain = (
            f"[0:v]crop={cw}:{ch}:{cx}:{cy},"
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h}[reframed]"
        )

    tail = f"fps={fps}"
    if zoom_times:
        z = _zoom_expr(zoom_times, fps)
        tail += (f",zoompan=z={z}"
                 f":x=(iw-iw/zoom)/2:y=(ih-ih/zoom)/2"
                 f":d=1:s={out_w}x{out_h}:fps={fps}")
    if with_captions:
        tail += f",subtitles=filename={ass_name}"
    return chain + f";[reframed]{tail}[vout]"


def render_clip(video_path: str, out_path: str, start: float, end: float,
                crop_spec: dict, ass_text: str, out_w: int = 1080,
                out_h: int = 1920, zoom_times: Optional[List[float]] = None,
                sfx: bool = False) -> None:
    """Render one clip. crop_spec comes from reframe.compute_crop_spec."""
    duration = max(end - start, 0.1)

    tmp_dir = tempfile.mkdtemp(prefix="opusfree_")
    ass_name = "captions.ass"
    with open(os.path.join(tmp_dir, ass_name), "w", encoding="utf-8") as fh:
        fh.write(ass_text)

    video_abs = os.path.abspath(video_path)
    out_abs = os.path.abspath(out_path)

    whoosh_path = os.path.join(tmp_dir, "whoosh.wav")
    use_sfx = bool(sfx and zoom_times) and _make_whoosh(whoosh_path)

    def _cmd(with_captions: bool) -> list[str]:
        fc = _build_video_chain(crop_spec, out_w, out_h, zoom_times,
                                ass_name, with_captions)
        inputs = ["-ss", f"{start:.3f}", "-i", video_abs,
                  "-t", f"{duration:.3f}"]
        maps = ["-map", "[vout]"]
        if use_sfx:
            n = len(zoom_times or [])
            delays = []
            for k, t in enumerate(zoom_times or []):
                ms = max(0, int((t - 0.35) * 1000))  # riser leads the zoom peak
                inputs += ["-i", whoosh_path]
                delays.append(f"[{k + 1}:a]adelay={ms}|{ms},volume=0.5[w{k}]")
            wlabels = "".join(f"[w{k}]" for k in range(n))
            fc += (";" + ";".join(delays) +
                   f";[0:a]{wlabels}amix=inputs={n + 1}"
                   f":duration=first:normalize=0[aout]")
            maps += ["-map", "[aout]"]
        else:
            maps += ["-map", "0:a?"]
        return (["ffmpeg", "-y"] + inputs +
                ["-filter_complex", fc] + maps +
                ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-c:a", "aac", "-b:a", "128k",
                 "-movflags", "+faststart", out_abs])

    try:
        try:
            subprocess.run(_cmd(True), check=True, capture_output=True,
                           text=True, cwd=tmp_dir)
        except subprocess.CalledProcessError as cap_exc:
            # Safety net: deliver the clip without captions rather than fail.
            last = (cap_exc.stderr.strip().splitlines()[-1]
                    if cap_exc.stderr else str(cap_exc))
            print(f"  [render] caption burn-in failed ({last}); "
                  "rendering without captions.")
            subprocess.run(_cmd(False), check=True, capture_output=True,
                           text=True, cwd=tmp_dir)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed:\n{exc.stderr[-1500:]}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
