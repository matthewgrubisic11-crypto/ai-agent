"""Orchestrate the full long-video -> viral-short pipeline (AI producer spec).

transcribe -> audio analysis -> arc-scored selection -> per clip: surgical EDL
(dead-air + filler removal, tightened timeline) -> reframe + multicam zoom +
kinetic captions + dialogue-enhanced audio render -> growth kit + directives ->
thumbnail. Emits clips.json matching the spec schema.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, List, Optional

from . import audio as audiomod
from .aspect import parse_ratio, ratio_tag, PLATFORM
from .captions import build_ass, POWER_WORDS
from .directives import (audio_directives, growth_kit, visual_directives)
from .edl import build_plan
from .llm import ollama_available
from .meta import generate_metadata
from .models import Clip, Word
from .reframe import compute_crop_spec
from .render import (ensure_ffmpeg, extract_thumbnail, probe_dimensions,
                     render_clip)
from .select import select_clips, select_by_prompt, EMOTION_WORDS
from .transcribe import transcribe

ProgressFn = Optional[Callable[[str, float, str], None]]


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (s[:40] or fallback)


def _noop(stage: str, pct: float, msg: str) -> None:
    print(f"[{pct:3.0f}%] {msg}")


def _tc(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def emphasis_times(words: List[Word], duration: float, max_count: int = 6,
                   min_spacing: float = 2.0) -> List[float]:
    """Output-timeline times of emphasis words -- multicam zoom / sfx anchors."""
    hits: List[float] = []
    for w in words:
        t = w.start
        if t < 1.2 or t > duration - 0.6:
            continue
        bare = w.text.lower().strip(".,!?;:\"'")
        if bare in POWER_WORDS or bare in EMOTION_WORDS or bare.isdigit():
            if not hits or t - hits[-1] >= min_spacing:
                hits.append(round(t, 2))
        if len(hits) >= max_count:
            break
    return hits


def process(video_path: str, out_dir: str, *, count: int = 10,
            min_dur: float = 20.0, max_dur: float = 60.0,
            model_size: str = "base", language: str | None = None,
            caption_style: str = "retention", use_llm: str | None = None,
            prompt: str | None = None, ratios: List[str] | None = None,
            gen_meta: bool = True, zooms: bool = True, sfx: bool = True,
            split_screen: bool = True, tighten: bool = True,
            enhance_audio: bool = True, music_path: str | None = None,
            on_progress: ProgressFn = None) -> List[dict]:
    """Run the whole pipeline; write clips + spec-format manifest to out_dir."""
    progress = on_progress or _noop
    ratios = ratios or ["9:16"]
    ensure_ffmpeg()
    os.makedirs(out_dir, exist_ok=True)

    if use_llm is None and ollama_available():
        use_llm = "ollama"
        progress("setup", 2, "Ollama detected — smarter selection + copy ON.")

    progress("transcribe", 5, f"Transcribing with whisper '{model_size}'...")
    transcript = transcribe(video_path, model_size=model_size, language=language)
    progress("transcribe", 26,
             f"{len(transcript.segments)} segments, {transcript.duration:.0f}s.")

    progress("analyze", 30, "Analyzing audio energy (spikes / thumbnail)...")
    alog = audiomod.amplitude_log(video_path)

    if prompt:
        progress("select", 34, f"ClipAnything search: {prompt!r}")
        clips = select_by_prompt(transcript, prompt, count=count, min_dur=min_dur,
                                 max_dur=max_dur, use_llm=use_llm)
    else:
        progress("select", 34, "Arc-scoring candidate moments...")
        clips = select_clips(transcript, count=count, min_dur=min_dur,
                             max_dur=max_dur, use_llm=use_llm)
    progress("select", 44, f"Selected {len(clips)} clips.")

    if not clips:
        progress("done", 100, "No clips met the arc/payoff bar. Loosen filters.")
        return []

    # Audio-spike boost: reward clips containing laughter/gasp energy spikes.
    for c in clips:
        c_energy = audiomod.window_energy(alog, c.start, c.end)
        if c_energy > 0.5:
            c.reasons.append("high audio energy")

    src_w, src_h = probe_dimensions(video_path)
    parsed = [(r, *parse_ratio(r)) for r in ratios]

    manifest: List[dict] = []
    total = len(clips)
    for i, clip in enumerate(clips, 1):
        base_pct = 44 + (i - 1) / total * 52
        progress("render", base_pct,
                 f"Clip {i}/{total}  score {clip.viral_score}/10  "
                 f"{clip.title[:40]}")

        # --- Surgical EDL + tightened timeline ---
        plan = build_plan(clip.words, clip.start, tighten=tighten)
        tight_words = plan.words                       # output-timeline words
        out_dur = (tight_words[-1].end if tight_words else clip.duration)
        # jump-cut points in the OUTPUT timeline (span boundaries)
        cut_points, acc = [], 0.0
        for (s, e) in plan.spans[:-1]:
            acc += (e - s)
            cut_points.append(round(acc, 2))
        z_times = emphasis_times(tight_words, out_dur) if zooms else []
        # ensure every jump cut is masked by a zoom (spec constraint)
        for cp in cut_points:
            if all(abs(cp - z) > 0.4 for z in z_times):
                z_times.append(cp)
        z_times = sorted(z_times)[:8]

        thumb_src = audiomod.peak_time(alog, clip.start, clip.end)
        thumb_name = f"{i:02d}_thumb.jpg"
        extract_thumbnail(video_path, thumb_src,
                          os.path.join(out_dir, thumb_name))

        if gen_meta:
            meta = generate_metadata(clip, platform=PLATFORM.get(ratios[0], "TikTok"),
                                     use_llm=use_llm)
            if meta.get("title"):
                clip.title = meta["title"]

        files, framing = {}, {}
        for ratio, out_w, out_h, value in parsed:
            spec = compute_crop_spec(video_path, clip.start, clip.end,
                                     src_w, src_h, target_ratio=out_w / out_h,
                                     allow_split=split_screen and value < 1)
            ass = build_ass(tight_words, 0.0, out_w, out_h, caption_style)
            name = (f"{i:02d}_score{clip.score}_{_slug(clip.title, f'clip{i}')}"
                    f"_{ratio_tag(ratio)}.mp4")
            render_clip(video_path, os.path.join(out_dir, name),
                        clip.start, clip.end, spec, ass,
                        out_w=out_w, out_h=out_h, spans=plan.spans,
                        zoom_times=z_times, sfx=sfx,
                        enhance_audio=enhance_audio, music_path=music_path)
            files[ratio] = name
            framing[ratio] = spec["mode"]

        # --- Spec-format record ---
        kit = growth_kit(clip, _tc(thumb_src - clip.start), use_llm=use_llm)
        record = {
            "clip_id": f"{i:03d}",
            "timeframes": {"start": _tc(clip.start), "end": _tc(clip.end)},
            "viral_score": clip.viral_score,
            "score_100": clip.score,
            "score_justification": clip.justification,
            "subscores": clip.subscores,
            "reasons": clip.reasons,
            "score_breakdown": clip.breakdown,
            "title": clip.title,
            "output_duration": round(out_dur, 2),
            "trimmed_seconds": plan.removed,
            "clean_transcript_edl": [
                {"word": e.word, "start": e.start, "end": e.end,
                 "action": e.action} for e in plan.edl],
            "visual_directives": visual_directives(tight_words, cut_points,
                                                   caption_style),
            "audio_directives": audio_directives(clip),
            "growth_kit": kit,
            "thumbnail": thumb_name,
            "files": files,
            "framing": framing,
            "zoom_moments": z_times,
        }
        if gen_meta:
            record["hashtags"] = meta.get("hashtags", [])
            sidecar = os.path.join(out_dir,
                                   f"{i:02d}_{_slug(clip.title, f'clip{i}')}.txt")
            with open(sidecar, "w", encoding="utf-8") as fh:
                titles = "\n".join("- " + t for t in kit["on_screen_titles"])
                fh.write(f"ON-SCREEN TITLES:\n{titles}\n\n"
                         f"CAPTION:\n{kit['post_caption']}\n")
        manifest.append(record)

    with open(os.path.join(out_dir, "clips.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    progress("done", 100,
             f"Done. {len(clips)} clips x {len(ratios)} ratio(s) in {out_dir}/")
    return manifest
