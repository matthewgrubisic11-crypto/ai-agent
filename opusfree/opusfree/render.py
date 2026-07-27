"""Render clips with ffmpeg: tight-cut assembly + reframe + multicam zoom +
kinetic captions + dialogue enhancement (+ optional sfx / music ducking).

The whole edit happens in one filter_complex:
  trim+concat kept spans (dead-air/filler removed) -> reframe (single crop or
  two-speaker split) -> simulated multicam zoom pulses centered on the eyes ->
  burn captions ;  audio: concat -> compress+loudnorm -> (optional) whoosh /
  ducked music mix.

Requires ffmpeg + ffprobe on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

from .audio import DIALOGUE_ENHANCE

FPS = 30


def ensure_ffmpeg() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise RuntimeError(
                f"'{binary}' not found on PATH. Install ffmpeg: "
                "https://ffmpeg.org/download.html")


def probe_dimensions(video_path: str) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", video_path],
        capture_output=True, text=True, check=True)
    stream = json.loads(out.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def extract_thumbnail(video_path: str, t: float, out_path: str) -> bool:
    """Grab a single high-quality JPG frame at source time ``t``."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", video_path,
             "-frames:v", "1", "-q:v", "2", out_path],
            check=True, capture_output=True, text=True)
        return os.path.exists(out_path)
    except subprocess.CalledProcessError:
        return False


def _zoom_expr(zoom_times: List[float], strength: float = 0.12) -> str:
    """Multicam punch: 100% wide baseline, ~112% pulses at each emphasis time."""
    pulses = "+".join(
        f"exp(-(on/{FPS}-{t:.2f})*(on/{FPS}-{t:.2f})/0.16)" for t in zoom_times)
    return f"1+{strength}*({pulses})"


def _make_whoosh(path: str, duration: float = 0.7) -> bool:
    expr = "0.22*sin(2*PI*(180+1500*t*t)*t)*sin(PI*t/0.7)"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", f"aevalsrc={expr}:d={duration}:s=44100",
             "-c:a", "pcm_s16le", path],
            check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _concat_chain(spans_rel: List[Tuple[float, float]]) -> Tuple[str, str, str]:
    """Trim+concat kept spans -> ([vc],[ac]) labels. Returns (chain, v, a)."""
    if len(spans_rel) <= 1:
        s, e = spans_rel[0] if spans_rel else (0.0, 0.0)
        chain = (f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[vc];"
                 f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[ac]")
        return chain, "[vc]", "[ac]"
    parts, labels = [], []
    for k, (s, e) in enumerate(spans_rel):
        parts.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{k}]")
        parts.append(f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[a{k}]")
        labels.append(f"[v{k}][a{k}]")
    n = len(spans_rel)
    parts.append(f"{''.join(labels)}concat=n={n}:v=1:a=1[vc][ac]")
    return ";".join(parts), "[vc]", "[ac]"


def _reframe_chain(vin: str, crop_spec: dict, out_w: int, out_h: int) -> str:
    if crop_spec["mode"] == "blur":
        # Full frame fit onto a blurred, dimmed fill of itself -- no blank walls.
        return (
            f"{vin}split=2[bg][fg];"
            f"[bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},boxblur=24:2,eq=brightness=-0.12[bgb];"
            f"[fg]scale={out_w}:-2:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[reframed]")
    if crop_spec["mode"] == "split":
        (w0, h0, x0, y0), (w1, h1, x1, y1) = crop_spec["crops"]
        half = out_h // 2
        return (
            f"{vin}split=2[p0][p1];"
            f"[p0]crop={w0}:{h0}:{x0}:{y0},"
            f"scale={out_w}:{half}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{half}[top];"
            f"[p1]crop={w1}:{h1}:{x1}:{y1},"
            f"scale={out_w}:{out_h - half}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h - half}[bot];"
            f"[top][bot]vstack=inputs=2[reframed]")
    cw, ch, cx, cy = crop_spec["crop"]
    return (f"{vin}crop={cw}:{ch}:{cx}:{cy},"
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h}[reframed]")


def render_clip(video_path: str, out_path: str, clip_start: float,
                clip_end: float, crop_spec: dict, ass_text: str,
                out_w: int = 1080, out_h: int = 1920,
                spans: Optional[List[Tuple[float, float]]] = None,
                zoom_times: Optional[List[float]] = None, sfx: bool = False,
                enhance_audio: bool = True,
                music_path: Optional[str] = None) -> None:
    """Render one finished clip. ``spans`` are source-absolute keep spans from
    the EDL (defaults to the whole clip). ``zoom_times`` are OUTPUT-timeline."""
    duration = max(clip_end - clip_start, 0.1)
    spans = spans or [(clip_start, clip_end)]
    spans_rel = [(max(0.0, s - clip_start), max(0.0, e - clip_start))
                 for s, e in spans]

    tmp_dir = tempfile.mkdtemp(prefix="opusfree_")
    ass_name = "captions.ass"
    with open(os.path.join(tmp_dir, ass_name), "w", encoding="utf-8") as fh:
        fh.write(ass_text)

    video_abs = os.path.abspath(video_path)
    out_abs = os.path.abspath(out_path)

    whoosh_path = os.path.join(tmp_dir, "whoosh.wav")
    use_sfx = bool(sfx and zoom_times) and _make_whoosh(whoosh_path)

    concat, vc, ac = _concat_chain(spans_rel)
    reframe = _reframe_chain(vc, crop_spec, out_w, out_h)

    def build(with_captions: bool) -> list[str]:
        vtail = f"[reframed]fps={FPS}"
        if zoom_times:
            z = _zoom_expr(zoom_times)
            vtail += (f",zoompan=z={z}"
                      f":x=(iw-iw/zoom)/2:y=(ih-ih/zoom)*0.42"
                      f":d=1:s={out_w}x{out_h}:fps={FPS}")
        if with_captions:
            vtail += f",subtitles=filename={ass_name}"
        vtail += "[vout]"

        # audio: enhance dialogue, then optional sfx / music ducking.
        # A pad label must be followed directly by a filter (no comma).
        atail = f"{ac}{DIALOGUE_ENHANCE if enhance_audio else 'anull'}[a0]"

        inputs = ["-ss", f"{clip_start:.3f}", "-i", video_abs,
                  "-t", f"{duration:.3f}"]
        extra_audio = []
        mix_labels = ["[a0]"]
        idx = 1

        if music_path and os.path.exists(music_path):
            inputs += ["-i", os.path.abspath(music_path)]
            # loop/trim music to length, duck under dialogue via sidechain
            extra_audio.append(
                f"[{idx}:a]aloop=loop=-1:size=2e9,atrim=0:{duration:.3f},"
                f"asetpts=PTS-STARTPTS,volume=0.35[music]")
            extra_audio.append(
                "[music][a0]sidechaincompress=threshold=0.03:ratio=6:"
                "attack=5:release=250[ducked]")
            mix_labels = ["[a0]", "[ducked]"]
            idx += 1

        if use_sfx:
            for k, t in enumerate(zoom_times or []):
                ms = max(0, int((t - 0.35) * 1000))
                inputs += ["-i", whoosh_path]
                extra_audio.append(
                    f"[{idx}:a]adelay={ms}|{ms},volume=0.5[w{k}]")
                mix_labels.append(f"[w{k}]")
                idx += 1

        fc = concat + ";" + reframe + ";" + vtail + ";" + atail
        if len(mix_labels) > 1:
            fc += ";" + ";".join(extra_audio)
            fc += (f";{''.join(mix_labels)}amix=inputs={len(mix_labels)}"
                   f":duration=first:normalize=0[aout]")
            amap = "[aout]"
        else:
            amap = "[a0]"

        return (["ffmpeg", "-y"] + inputs +
                ["-filter_complex", fc, "-map", "[vout]", "-map", amap,
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                 out_abs])

    try:
        try:
            subprocess.run(build(True), check=True, capture_output=True,
                           text=True, cwd=tmp_dir)
        except subprocess.CalledProcessError as cap_exc:
            last = (cap_exc.stderr.strip().splitlines()[-1]
                    if cap_exc.stderr else str(cap_exc))
            print(f"  [render] caption burn-in failed ({last}); "
                  "rendering without captions.")
            subprocess.run(build(False), check=True, capture_output=True,
                           text=True, cwd=tmp_dir)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed:\n{exc.stderr[-1800:]}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
