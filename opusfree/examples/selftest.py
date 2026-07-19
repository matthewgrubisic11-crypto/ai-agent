"""Logic-only self-test (no ffmpeg/whisper/opencv needed)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opusfree.models import Word, Segment, Transcript
from opusfree.select import select_clips
from opusfree.captions import build_ass


def main() -> None:
    script = ("here is the biggest mistake everyone makes with money and why it "
              "is wrong . the secret is you always need to start now honestly . "
              "imagine what happens when you never stop learning about this .")
    words, t = [], 0.0
    for tok in script.split():
        words.append(Word(text=tok, start=t, end=t + 0.4))
        t += 0.45
    tr = Transcript(segments=[Segment(text=script, start=0.0, end=t, words=words)])

    clips = select_clips(tr, count=3, min_dur=2.0, max_dur=20.0)
    print("clips selected:", len(clips))
    for c in clips:
        print(f"  score={c.score} dur={c.duration:.1f}s "
              f"title={c.title!r} reasons={c.reasons}")
    assert clips and all(1 <= c.score <= 100 for c in clips)

    ass = build_ass(clips[0].words, clips[0].start, 1080, 1920, "hormozi")
    assert "Dialogue:" in ass
    assert "\\kf" in ass
    print("ASS dialogue lines:", ass.count("Dialogue:"))
    print("SELF-TEST OK")


if __name__ == "__main__":
    main()
