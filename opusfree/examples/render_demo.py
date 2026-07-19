"""Prove the render path (reframe + captions + ffmpeg export) on a real video.

Skips only the Whisper download (blocked in some sandboxes) by supplying a
transcript directly, then runs the exact production stages: scoring, OpenCV
reframe, ASS captions, and ffmpeg encode. Usage:
    python examples/render_demo.py <video> <script.txt> <out_dir>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opusfree.models import Word, Segment, Transcript
from opusfree.render import probe_dimensions
from opusfree.select import select_clips
from opusfree.pipeline import process  # noqa: F401  (import sanity)
from opusfree.reframe import compute_crop
from opusfree.captions import build_ass
from opusfree.render import render_clip
from opusfree.aspect import parse_ratio, ratio_tag
from opusfree.meta import generate_metadata
import subprocess
import json


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def build_transcript(script_path, total):
    """Evenly distribute words across the audio to fake word timings."""
    text = open(script_path).read().replace("\n", " ")
    tokens = text.split()
    per = total / max(len(tokens), 1)
    words, t = [], 0.0
    for tok in tokens:
        words.append(Word(text=tok, start=round(t, 3), end=round(t + per * 0.9, 3)))
        t += per
    # One big segment split on sentence-ending tokens.
    segs, cur, seg_start = [], [], 0.0
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
    print(f"transcript: {len(tr.segments)} segments over {total:.1f}s")

    clips = select_clips(tr, count=3, min_dur=8.0, max_dur=25.0)
    print(f"selected {len(clips)} clips")
    src_w, src_h = probe_dimensions(video)

    manifest = []
    for i, clip in enumerate(clips, 1):
        meta = generate_metadata(clip, "TikTok")
        clip.title = meta["title"]
        print(f"  clip {i}: score {clip.score}  {clip.duration:.0f}s  {clip.title[:45]}")
        files = {}
        for ratio in ("9:16", "1:1"):
            ow, oh, _ = parse_ratio(ratio)
            crop = compute_crop(video, clip.start, clip.end, src_w, src_h, ow / oh)
            ass = build_ass(clip.words, clip.start, ow, oh, "bold-yellow")
            name = f"{i:02d}_score{clip.score}_{ratio_tag(ratio)}.mp4"
            render_clip(video, os.path.join(out_dir, name), clip.start, clip.end,
                        crop, ass, ow, oh)
            files[ratio] = name
        manifest.append({"score": clip.score, "title": clip.title,
                         "hashtags": meta["hashtags"], "files": files})

    json.dump(manifest, open(os.path.join(out_dir, "clips.json"), "w"), indent=2)
    print("RENDER DEMO OK")


if __name__ == "__main__":
    main()
