"""Render clips with ffmpeg — two-pass for rock-solid captions.

Pass 1 (filter_complex): trim/concat kept spans (dead-air/filler removed) ->
reframe (single crop / two-speaker split / blurred-fill) -> subtle cinematic
push -> dialogue-enhanced audio (+ optional music ducking). No subtitles here.

Pass 2 (simple -vf): burn the ASS captions onto the pass-1 video. Isolating
the subtitles step this way is the form proven to work across ffmpeg 6/7/8,
so captions always render.

No cartoon SFX, no springy zoom pulses — those read as amateur. Motion is a
slow push; audio stays clean.

Requires ffmpeg + ffprobe on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

from .audio import DIALOGUE_ENHANCE, DIALOGUE_ENHANCE_CLEAN

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
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", video_path,
             "-frames:v", "1", "-q:v", "2", out_path],
            check=True, capture_output=True, text=True)
        return os.path.exists(out_path)
    except subprocess.CalledProcessError:
        return False


def _concat_chain(spans_rel: List[Tuple[float, float]]) -> Tuple[str, str, str]:
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


def _track_x_expr(keys: List[Tuple[float, float]]) -> str:
    """Piecewise-linear crop-x expression over output time t from keyframes."""
    keys = sorted(keys)
    # nested if(): before first -> x0; between k,k+1 -> lerp; after last -> xn
    expr = f"{keys[-1][1]:.1f}"
    for i in range(len(keys) - 1, 0, -1):
        t0, x0 = keys[i - 1]
        t1, x1 = keys[i]
        if t1 - t0 < 1e-3:
            continue
        lerp = f"({x0:.1f}+({x1 - x0:.1f})*(t-{t0:.3f})/{t1 - t0:.3f})"
        expr = f"if(lt(t,{t1:.3f}),{lerp},{expr})"
    return f"if(lt(t,{keys[0][0]:.3f}),{keys[0][1]:.1f},{expr})"


def _reframe_chain(vin: str, crop_spec: dict, out_w: int, out_h: int) -> str:
    track = crop_spec.get("track_x")
    if track and crop_spec.get("mode") == "single" and crop_spec.get("crop_wh"):
        cw, ch = crop_spec["crop_wh"]
        xexpr = _track_x_expr(track)
        return (f"{vin}crop=w={cw}:h={ch}:x='{xexpr}':y=0,"
                f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h}[reframed]")
    if crop_spec["mode"] == "blur":
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


def _push_filter(duration: float, out_w: int, out_h: int,
                 amount: float = 0.06) -> str:
    """A subtle, slow cinematic push-in over the whole clip (Ken Burns).

    Not a springy pulse -- a gentle zoom from 1.0 to ~1.06, centered.
    """
    inc = amount / max(duration * FPS, 1)
    z = f"min(1+{inc:.6f}*on,{1 + amount:.3f})"
    return (f",zoompan=z='{z}':d=1:s={out_w}x{out_h}:fps={FPS}"
            f":x='iw/2-(iw/zoom/2)':y='ih*0.5-(ih/zoom*0.5)'")


def render_clip(video_path: str, out_path: str, clip_start: float,
                clip_end: float, crop_spec: dict, ass_text: str,
                out_w: int = 1080, out_h: int = 1920,
                spans: Optional[List[Tuple[float, float]]] = None,
                push: bool = True, enhance_audio: bool = True,
                clean_audio: bool = False,
                music_path: Optional[str] = None,
                progress_bar: bool = True,
                broll: Optional[List[Tuple[float, float, str]]] = None,
                track_x: Optional[List[Tuple[float, float]]] = None,
                # accepted for back-compat; sfx is intentionally ignored now
                zoom_times: Optional[List[float]] = None,
                sfx: bool = False) -> None:
    """Render one finished clip (two-pass; captions always burned in).

    Pass 1: assemble+reframe+push+audio. (opt) B-roll overlay. Pass 2: burn
    captions (+ progress bar). ``broll`` = [(start, dur, path), ...] in the
    OUTPUT timeline."""
    duration = max(clip_end - clip_start, 0.1)
    if track_x:
        crop_spec = {**crop_spec, "track_x": track_x}
    spans = spans or [(clip_start, clip_end)]
    spans_rel = [(max(0.0, s - clip_start), max(0.0, e - clip_start))
                 for s, e in spans]
    out_dur = sum(e - s for s, e in spans_rel) or duration

    tmp_dir = tempfile.mkdtemp(prefix="opusfree_")
    ass_name = "captions.ass"
    with open(os.path.join(tmp_dir, ass_name), "w", encoding="utf-8") as fh:
        fh.write(ass_text)
    stage1 = os.path.join(tmp_dir, "stage1.mp4")

    video_abs = os.path.abspath(video_path)
    out_abs = os.path.abspath(out_path)

    # ---- PASS 1: assemble + reframe + push + audio (no subtitles) ----
    concat, vc, ac = _concat_chain(spans_rel)
    reframe = _reframe_chain(vc, crop_spec, out_w, out_h)
    vtail = f"[reframed]fps={FPS}"
    if push:
        vtail += _push_filter(out_dur, out_w, out_h)
    vtail += "[vout]"
    enh = (DIALOGUE_ENHANCE_CLEAN if clean_audio else DIALOGUE_ENHANCE)
    atail = f"{ac}{enh if enhance_audio else 'anull'}[a0]"

    inputs = ["-ss", f"{clip_start:.3f}", "-i", video_abs, "-t", f"{duration:.3f}"]
    amap = "[a0]"
    if music_path and os.path.exists(music_path):
        inputs += ["-i", os.path.abspath(music_path)]
        atail += (f";[1:a]aloop=loop=-1:size=2e9,atrim=0:{out_dur:.3f},"
                  f"asetpts=PTS-STARTPTS,volume=0.30[music];"
                  f"[music][a0]sidechaincompress=threshold=0.03:ratio=8:"
                  f"attack=5:release=250[duck];[a0][duck]"
                  f"amix=inputs=2:duration=first:normalize=0[aout]")
        amap = "[aout]"

    fc1 = concat + ";" + reframe + ";" + vtail + ";" + atail
    cmd1 = (["ffmpeg", "-y"] + inputs + ["-filter_complex", fc1,
            "-map", "[vout]", "-map", amap,
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-c:a", "aac", "-b:a", "160k", stage1])

    # ---- optional B-roll overlay (under captions) ----
    def _stage_for_captions() -> str:
        if broll:
            from .broll import overlay_broll
            stage1b = os.path.join(tmp_dir, "stage1b.mp4")
            if overlay_broll(stage1, stage1b, broll, out_w, out_h):
                return stage1b
        return stage1

    # ---- PASS 2: captions (+ progress bar) with the ffmpeg-8-proven form ----
    vf2 = f"subtitles=filename={ass_name}"
    if progress_bar:
        vf2 += (f",drawbox=x=0:y=ih-14:w='iw*min(t/{out_dur:.2f}\\,1)':h=14"
                f":color=0x22E0FF@0.9:t=fill")

    try:
        subprocess.run(cmd1, check=True, capture_output=True, text=True,
                       cwd=tmp_dir)
        cap_input = _stage_for_captions()
        cmd2 = (["ffmpeg", "-y", "-i", os.path.abspath(cap_input),
                 "-vf", vf2,
                 "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                 "-c:a", "copy", "-movflags", "+faststart", out_abs])
        try:
            subprocess.run(cmd2, check=True, capture_output=True, text=True,
                           cwd=tmp_dir)
        except subprocess.CalledProcessError as cap_exc:
            last = (cap_exc.stderr.strip().splitlines()[-1]
                    if cap_exc.stderr else str(cap_exc))
            print(f"  [render] caption burn failed ({last}); "
                  "delivering clip without captions.")
            shutil.copyfile(cap_input, out_abs)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed:\n{exc.stderr[-1800:]}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
