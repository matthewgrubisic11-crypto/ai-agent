"""Orchestrate the full long-video -> short-clips pipeline."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from typing import Callable, List, Optional

from .aspect import parse_ratio, ratio_tag, PLATFORM
from .captions import build_ass
from .meta import generate_metadata
from .models import Clip
from .reframe import compute_crop
from .render import ensure_ffmpeg, probe_dimensions, render_clip
from .select import select_clips, select_by_prompt
from .transcribe import transcribe

ProgressFn = Optional[Callable[[str, float, str], None]]


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (s[:40] or fallback)


def _noop(stage: str, pct: float, msg: str) -> None:
    print(f"[{pct:3.0f}%] {msg}")


def process(video_path: str, out_dir: str, *, count: int = 10,
            min_dur: float = 15.0, max_dur: float = 60.0,
            model_size: str = "base", language: str | None = None,
            caption_style: str = "bold-yellow", use_llm: str | None = None,
            prompt: str | None = None, ratios: List[str] | None = None,
            gen_meta: bool = True, on_progress: ProgressFn = None) -> List[dict]:
    """Run the whole pipeline; write clips + a manifest to ``out_dir``.

    Returns the manifest (list of dicts). ``ratios`` is a list like
    ['9:16', '1:1']; each clip is rendered in every ratio. ``prompt`` switches
    on ClipAnything-style selection.
    """
    progress = on_progress or _noop
    ratios = ratios or ["9:16"]
    ensure_ffmpeg()
    os.makedirs(out_dir, exist_ok=True)

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
    parsed = [(r, *parse_ratio(r)) for r in ratios]  # (ratio, w, h, value)

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

        for ratio, out_w, out_h, value in parsed:
            name = (f"{i:02d}_score{clip.score}_{_slug(clip.title, f'clip{i}')}"
                    f"_{ratio_tag(ratio)}.mp4")
            out_path = os.path.join(out_dir, name)
            crop = compute_crop(video_path, clip.start, clip.end, src_w, src_h,
                                target_ratio=out_w / out_h)
            ass = build_ass(clip.words, clip.start, out_w, out_h, caption_style)
            render_clip(video_path, out_path, clip.start, clip.end, crop, ass,
                        out_w=out_w, out_h=out_h)
            entry["files"][ratio] = name

        # Write a sidecar with ready-to-paste social copy.
        if gen_meta:
            sidecar = os.path.join(out_dir, f"{i:02d}_{_slug(clip.title, f'clip{i}')}.txt")
            with open(sidecar, "w", encoding="utf-8") as fh:
                fh.write(f"{entry.get('title','')}\n\n{entry.get('description','')}\n\n"
                         f"{' '.join(entry.get('hashtags', []))}\n")

        manifest.append(entry)

    with open(os.path.join(out_dir, "clips.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    progress("done", 100, f"Done. {len(clips)} clips x {len(ratios)} ratio(s) in {out_dir}/")
    return manifest
