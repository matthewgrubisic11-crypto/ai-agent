"""End-to-end render proof of the AI-producer pipeline (no Whisper needed).

Builds a transcript with deliberate filler words + pauses, then runs the real
stages: arc scoring, surgical EDL, tightened render (trim/concat), multicam
zoom, kinetic captions, dialogue enhancement, directives + growth kit + thumb.
    python examples/render_demo.py <video> <script.txt> <out_dir>
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opusfree.models import Word, Segment, Transcript
from opusfree.render import probe_dimensions, render_clip, extract_thumbnail
from opusfree.select import select_clips
from opusfree.reframe import compute_crop_spec
from opusfree.captions import build_ass
from opusfree.aspect import parse_ratio, ratio_tag
from opusfree.edl import build_plan
from opusfree.directives import visual_directives, growth_kit, audio_directives
from opusfree.pipeline import emphasis_times
from opusfree import audio as audiomod


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def build_transcript(script_path, total):
    text = open(script_path).read().replace("\n", " ")
    tokens = text.split()
    per = total / max(len(tokens), 1)
    words, t = [], 0.0
    for tok in tokens:
        # inject a fake long pause after "..." markers
        if tok == "<pause>":
            t += 0.8
            continue
        words.append(Word(text=tok, start=round(t, 3), end=round(t + per * 0.8, 3)))
        t += per
    segs, cur = [], []
    for w in words:
        cur.append(w)
        if w.text[-1:] in ".!?":
            segs.append(Segment(text=" ".join(x.text for x in cur),
                                start=cur[0].start, end=cur[-1].end, words=cur))
            cur = []
    if cur:
        segs.append(Segment(text=" ".join(x.text for x in cur),
                            start=cur[0].start, end=cur[-1].end, words=cur))
    return Transcript(segments=segs)


def main():
    video, script, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    total = duration(video)
    tr = build_transcript(script, total)
    alog = audiomod.amplitude_log(video)
    print(f"transcript: {len(tr.segments)} segments, {len(alog)} amp windows")

    clips = select_clips(tr, count=2, min_dur=6.0, max_dur=40.0, strict_arc=False)
    print(f"selected {len(clips)} clips")
    src_w, src_h = probe_dimensions(video)

    manifest = []
    for i, clip in enumerate(clips, 1):
        plan = build_plan(clip.words, clip.start, tighten=True)
        out_dur = plan.words[-1].end if plan.words else clip.duration
        cut_points, acc = [], 0.0
        for (s, e) in plan.spans[:-1]:
            acc += (e - s)
            cut_points.append(round(acc, 2))
        z = emphasis_times(plan.words, out_dur)
        for cp in cut_points:
            if all(abs(cp - x) > 0.4 for x in z):
                z.append(cp)
        z = sorted(z)[:8]
        thumb = audiomod.peak_time(alog, clip.start, clip.end)
        extract_thumbnail(video, thumb, os.path.join(out_dir, f"{i:02d}_thumb.jpg"))

        print(f"  clip {i}: {clip.viral_score}/10  removed {plan.removed}s  "
              f"{len(plan.spans)} spans  zooms@{z}")
        ow, oh, _ = parse_ratio("9:16")
        spec = compute_crop_spec(video, clip.start, clip.end, src_w, src_h, ow / oh)
        ass = build_ass(plan.words, 0.0, ow, oh, "retention")
        name = f"{i:02d}_score{clip.score}_9x16.mp4"
        render_clip(video, os.path.join(out_dir, name), clip.start, clip.end,
                    spec, ass, ow, oh, spans=plan.spans, zoom_times=z, sfx=True,
                    enhance_audio=True)
        manifest.append({
            "clip_id": f"{i:03d}", "viral_score": clip.viral_score,
            "score_justification": clip.justification,
            "subscores": clip.subscores,
            "clean_transcript_edl": [
                {"word": e.word, "action": e.action} for e in plan.edl][:12],
            "visual_directives": visual_directives(plan.words, cut_points,
                                                   "retention")[:5],
            "audio_directives": audio_directives(clip),
            "growth_kit": growth_kit(clip, "00:00:02.00"),
            "file": name,
        })
    json.dump(manifest, open(os.path.join(out_dir, "clips.json"), "w"), indent=2)
    print("RENDER DEMO OK")
    print(json.dumps(manifest[0], indent=2)[:900])


if __name__ == "__main__":
    main()
