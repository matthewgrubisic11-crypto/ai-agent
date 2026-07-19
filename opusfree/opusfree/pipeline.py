"""Orchestrate the full long-video -> short-clips pipeline."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from typing import Callable, List, Optional

from .aspect import parse_ratio, ratio_tag, PLATFORM
from .captions import build_ass, POWER_WORDS
from .llm import ollama_available
from .meta import generate_metadata
from .models import Clip
from .reframe import compute_crop_spec
from .render import ensure_ffmpeg, probe_dimensions, render_clip
from .select import select_clips, select_by_prompt, EMOTION_WORDS
from .transcribe import transcribe

ProgressFn = Optional[Callable[[str, float, str], None]]


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (s[:40] or fallback)


def _noop(stage: str, pct: float, msg: str) -> None:
    print(f"[{pct:3.0f}%] {msg}")


def emphasis_times(clip: Clip, max_count: int = 4,
                   min_spacing: float = 4.0) -> List[float]:
    """Clip-relative times of emphasis words -- where punch zooms land.

    Skips the first two seconds (let the hook breathe) and enforces spacing
    so the effect stays an accent, not a seizure.
    """
    hits: List[float] = []
    for w in clip.words:
        t = w.start - clip.start
        if t < 2.0 or t > clip.duration - 1.0:
            continue
        bare = w.text.lower().strip(".,!?;:\"'")
        if bare in POWER_WORDS or bare in EMOTION_WORDS or bare.isdigit():
            if not hits or t - hits[-1] >= min_spacing:
                hits.append(round(t, 2))
        if len(hits) >= max_count:
            break
    return hits


def process(video_path: str, out_dir: str, *, count: int = 10,
            min_dur: float = 15.0, max_dur: float = 60.0,
            model_size: str = "base", language: str | None = None,
            caption_style: str = "retention", use_llm: str | None = None,
            prompt: str | None = None, ratios: List[str] | None = None,
            gen_meta: bool = True, zooms: bool = True, sfx: bool = True,
            split_screen: bool = True,
            on_progress: ProgressFn = None) -> List[dict]:
    """Run the whole pipeline; write clips + a manifest to ``out_dir``."""
    progress = on_progress or _noop
    ratios = ratios or ["9:16"]
    ensure_ffmpeg()
    os.makedirs(out_dir, exist_ok=True)

    # Auto-upgrade brains: if Ollama is running locally, use it.
    if use_llm is None and ollama_available():
        use_llm = "ollama"
        progress("setup", 2, "Ollama detected — smarter AI clip selection ON.")

    progress("transcribe", 5, f"Transcribing with whisper '{model_size}'...")
    transcript = transcribe(video_path, model_size=model_size, language=language)
    progress("transcribe", 30,
             f"{len(transcript.segments)} segments, {transcript.duration:.0f}s audio.")

    if prompt:
        progress("select", 35, f"ClipAnything search: {prompt!r}")
        clips = select_by_prompt(transcript, prompt, count=count, min_dur=min_dur,
                                 max_dur=max_dur, use_llm=use_llm)
    else:
        progress("select", 35, "Scoring candidate moments...")
        clips = select_clips(transcript, count=count, min_dur=min_dur,
                             max_dur=max_dur, use_llm=use_llm)
    progress("select", 45, f"Selected {len(clips)} clips.")

    if not clips:
        progress("done", 100, "No clips matched. Try a broader prompt or range.")
        return []

    src_w, src_h = probe_dimensions(video_path)
    parsed = [(r, *parse_ratio(r)) for r in ratios]

    manifest: List[dict] = []
    total = len(clips)
    for i, clip in enumerate(clips, 1):
        base_pct = 45 + (i - 1) / total * 50
        progress("render", base_pct,
                 f"Clip {i}/{total}  score {clip.score}  {clip.title[:44]}")

        entry = asdict(clip)
        if gen_meta:
            meta = generate_metadata(clip, platform=PLATFORM.get(ratios[0], "TikTok"),
                                     use_llm=use_llm)
            entry.update(meta)
            if meta.get("title"):
                clip.title = meta["title"]
        entry["files"] = {}

        z_times = emphasis_times(clip) if zooms else []
        entry["zoom_moments"] = z_times

        for ratio, out_w, out_h, value in parsed:
            spec = compute_crop_spec(video_path, clip.start, clip.end,
                                     src_w, src_h, target_ratio=out_w / out_h,
                                     allow_split=split_screen and value < 1)
            ass = build_ass(clip.words, clip.start, out_w, out_h, caption_style)
            name = (f"{i:02d}_score{clip.score}_{_slug(clip.title, f'clip{i}')}"
                    f"_{ratio_tag(ratio)}.mp4")
            render_clip(video_path, os.path.join(out_dir, name),
                        clip.start, clip.end, spec, ass,
                        out_w=out_w, out_h=out_h,
                        zoom_times=z_times, sfx=sfx)
            entry["files"][ratio] = name
            entry.setdefault("framing", {})[ratio] = spec["mode"]

        if gen_meta:
            sidecar = os.path.join(out_dir,
                                   f"{i:02d}_{_slug(clip.title, f'clip{i}')}.txt")
            with open(sidecar, "w", encoding="utf-8") as fh:
                fh.write(f"{entry.get('title','')}\n\n{entry.get('description','')}\n\n"
                         f"{' '.join(entry.get('hashtags', []))}\n")

        manifest.append(entry)

    with open(os.path.join(out_dir, "clips.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    progress("done", 100,
             f"Done. {len(clips)} clips x {len(ratios)} ratio(s) in {out_dir}/")
    return manifest
