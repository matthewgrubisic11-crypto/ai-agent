"""Logic-only self-test (no ffmpeg/whisper/opencv needed)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opusfree.models import Word, Segment, Transcript
from opusfree.select import select_clips, select_by_prompt
from opusfree.captions import build_ass
from opusfree.aspect import parse_ratio, ratio_tag
from opusfree.meta import generate_metadata
from opusfree.multipart import parse as parse_multipart


def _fake_transcript() -> Transcript:
    script = ("here is the biggest mistake everyone makes with money and why it "
              "is wrong . the secret to pricing is you always need to charge more "
              "honestly . imagine what happens when you never stop learning about "
              "marketing and growth for your startup today .")
    words, t = [], 0.0
    for tok in script.split():
        words.append(Word(text=tok, start=t, end=t + 0.4))
        t += 0.45
    return Transcript(segments=[Segment(text=script, start=0.0, end=t, words=words)])


def main() -> None:
    tr = _fake_transcript()

    # 1. Virality selection
    clips = select_clips(tr, count=3, min_dur=2.0, max_dur=20.0)
    assert clips and all(1 <= c.score <= 100 for c in clips)
    print(f"virality select: {len(clips)} clips, top score {clips[0].score}")

    # 2. ClipAnything prompt selection
    pclips = select_by_prompt(tr, "pricing and charging money", count=3,
                              min_dur=2.0, max_dur=20.0)
    print(f"ClipAnything 'pricing': {len(pclips)} clips",
          [c.title[:30] for c in pclips])
    assert any("pricing" in c.text or "charge" in c.text for c in pclips)

    # 3. Captions
    ass = build_ass(clips[0].words, clips[0].start, 1080, 1920, "hormozi")
    assert "Dialogue:" in ass and "\\kf" in ass
    print(f"captions: {ass.count('Dialogue:')} dialogue lines")

    # 4. Aspect ratios
    for r, exp_ratio in [("9:16", 9 / 16), ("1:1", 1.0), ("16:9", 16 / 9)]:
        w, h, val = parse_ratio(r)
        assert abs(w / h - exp_ratio) < 0.02, (r, w, h)
        assert w % 2 == 0 and h % 2 == 0
    print("aspect ratios:", parse_ratio("9:16"), parse_ratio("1:1"),
          parse_ratio("16:9"), "tag=", ratio_tag("9:16"))

    # 5. Metadata (heuristic path)
    meta = generate_metadata(clips[0], platform="TikTok")
    assert meta["title"] and meta["hashtags"]
    print("metadata:", meta["title"][:40], "|", " ".join(meta["hashtags"][:4]))

    # 6. Multipart parser
    boundary = "X"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="count"\r\n\r\n'
        "7\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="video"; filename="a.mp4"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
    ).encode() + b"\x00\x01BINARY\x02" + f"\r\n--{boundary}--\r\n".encode()
    fields, upload = parse_multipart(body, f"multipart/form-data; boundary={boundary}")
    assert fields["count"] == "7"
    assert upload and upload[0] == "a.mp4" and b"BINARY" in upload[1]
    print("multipart: field count=7, file a.mp4", len(upload[1]), "bytes")

    print("SELF-TEST OK")


if __name__ == "__main__":
    main()
