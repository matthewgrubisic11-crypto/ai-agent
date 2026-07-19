"""Orchestrate the full long-video -> short-clips pipeline."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from typing import List

from .captions import build_ass
from .models import Clip
from .reframe import compute_crop
from .render import ensure_ffmpeg, probe_dimensions, render_clip
from .select import select_clips
from .transcribe import transcribe


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (s[:40] or fallback)


def process(video_path: str, out_dir: str, *, count: int = 10,
            min_dur: float = 15.0, max_dur: float = 60.0,
            model_size: str = "base", language: str | None = None,
            caption_style: str = "bold-yellow", use_llm: str | None = None,
            out_w: int = 1080, out_h: int = 1920) -> List[Clip]:
    """Run the whole pipeline and write clips + a manifest to ``out_dir``."""
    ensure_ffmpeg()
    os.makedirs(out_dir, exist_ok=True)

    print(f"[1/4] Transcribing with whisper '{model_size}' (local)...")
    transcript = transcribe(video_path, model_size=model_size, language=language)
    print(f"      {len(transcript.segments)} segments, "
          f"{transcript.duration:.0f}s of audio.")

    print(f"[2/4] Scoring candidate moments"
          f"{' + ollama rerank' if use_llm == 'ollama' else ''}...")
    clips = select_clips(transcript, count=count, min_dur=min_dur,
                         max_dur=max_dur, use_llm=use_llm)
    print(f"      Selected top {len(clips)} clips.")

    src_w, src_h = probe_dimensions(video_path)

    manifest = []
    for i, clip in enumerate(clips, 1):
        name = f"{i:02d}_score{clip.score}_{_slug(clip.title, f'clip{i}')}.mp4"
        out_path = os.path.join(out_dir, name)
        print(f"[3/4] Clip {i}/{len(clips)}  score {clip.score:>3}  "
              f"{clip.duration:>4.0f}s  {clip.title[:48]}")

        crop = compute_crop(video_path, clip.start, clip.end, src_w, src_h,
                            target_ratio=out_w / out_h)
        ass = build_ass(clip.words, clip.start, out_w, out_h, caption_style)
        render_clip(video_path, out_path, clip.start, clip.end, crop, ass,
                    out_w=out_w, out_h=out_h)

        entry = asdict(clip)
        entry["file"] = name
        manifest.append(entry)

    manifest_path = os.path.join(out_dir, "clips.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    print(f"[4/4] Done. {len(clips)} clips + manifest in {out_dir}/")

    return clips
