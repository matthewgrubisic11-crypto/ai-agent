"""Retention-focused animated captions as ASS subtitles.

What keeps viewers watching (short-form best practice):
- BIG type near the vertical center -- not the bottom, where platform UI sits
- 1-3 words on screen at a time, so the eye keeps tracking
- the word being spoken highlights (karaoke), power words get an accent color
- a quick pop-in scale animation on each phrase
- heavy outline/shadow so text stays readable over any footage

Each style below encodes those choices; "retention" is the default and the
most aggressive about them. Rendering is ffmpeg/libass in render.py.
"""

from __future__ import annotations

from typing import List

from .models import Word

# Words that deserve the accent color (emphasis) inside captions.
POWER_WORDS = {
    "never", "always", "everyone", "nobody", "biggest", "worst", "best",
    "most", "secret", "truth", "mistake", "money", "free", "stop", "now",
    "insane", "crazy", "huge", "massive", "important", "powerful", "wrong",
    "right", "million", "billion", "first", "last", "hate", "love", "fear",
    "win", "lose", "amazing", "incredible", "changed", "warning",
}

# Colors are ASS &HBBGGRR (no alpha here; alpha added where needed).
STYLES = {
    # The default: big, centered, punchy. Modeled on high-retention shorts.
    "retention": {
        "font": "Arial Black", "size_frac": 0.052, "margin_frac": 0.30,
        "primary": "FFFFFF", "highlight": "00E9FF",   # yellow highlight
        "accent": "00FF7F",                            # spring green power words
        "outline": "000000", "outline_w": 5, "shadow": 2,
        "uppercase": True, "max_words": 3, "max_dur": 1.6, "pop": True,
    },
    # White, cleaner, a bit smaller; still center-ish.
    "clean-white": {
        "font": "Arial", "size_frac": 0.040, "margin_frac": 0.26,
        "primary": "FFFFFF", "highlight": "00D7FF",
        "accent": "00D7FF",
        "outline": "202020", "outline_w": 3, "shadow": 1,
        "uppercase": False, "max_words": 4, "max_dur": 2.2, "pop": False,
    },
    # Classic bold-yellow karaoke look.
    "bold-yellow": {
        "font": "Arial Black", "size_frac": 0.044, "margin_frac": 0.22,
        "primary": "FFFFFF", "highlight": "00F0FF",
        "accent": "00F0FF",
        "outline": "000000", "outline_w": 4, "shadow": 1,
        "uppercase": False, "max_words": 4, "max_dur": 2.4, "pop": False,
    },
    # Green-highlight, huge, all-caps.
    "hormozi": {
        "font": "Arial Black", "size_frac": 0.055, "margin_frac": 0.30,
        "primary": "FFFFFF", "highlight": "00FF00",
        "accent": "00FF00",
        "outline": "000000", "outline_w": 6, "shadow": 2,
        "uppercase": True, "max_words": 3, "max_dur": 1.8, "pop": True,
    },
}


def _fmt_ts(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs == 100:
        cs = 99
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _chunk_words(words: List[Word], max_words: int, max_dur: float
                 ) -> List[List[Word]]:
    chunks: List[List[Word]] = []
    cur: List[Word] = []
    for w in words:
        if cur and (len(cur) >= max_words or
                    (w.end - cur[0].start) > max_dur or
                    cur[-1].text[-1:] in ".!?"):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words: List[Word], clip_start: float, video_w: int, video_h: int,
              style_name: str = "retention") -> str:
    """Return ASS subtitle text; word times are shifted to clip-relative."""
    st = STYLES.get(style_name, STYLES["retention"])
    size = max(28, int(video_h * st["size_frac"]))
    margin_v = int(video_h * st["margin_frac"])

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{st['font']},{size},&H00{st['primary']},&H00{st['highlight']},&H00{st['outline']},&H80000000,-1,0,0,0,100,100,0,0,1,{st['outline_w']},{st['shadow']},2,40,40,{margin_v},1
"""

    # Pop-in: start slightly small, snap to full size in ~120ms.
    pop_tag = (r"{\fscx82\fscy82\t(0,120,\fscx100\fscy100)}"
               if st["pop"] else "")

    lines = []
    for chunk in _chunk_words(words, st["max_words"], st["max_dur"]):
        c_start = chunk[0].start - clip_start
        c_end = chunk[-1].end - clip_start
        parts = [pop_tag]
        for i, w in enumerate(chunk):
            nxt = chunk[i + 1].start if i + 1 < len(chunk) else w.end
            k_cs = max(1, int(round((nxt - w.start) * 100)))
            text = w.text.replace("{", "(").replace("}", ")")
            if st["uppercase"]:
                text = text.upper()
            bare = w.text.lower().strip(".,!?;:\"'")
            if bare in POWER_WORDS or bare.rstrip("%$").isdigit():
                # Accent color for power words / numbers, then reset.
                parts.append(
                    rf"{{\kf{k_cs}\1c&H{st['accent']}&}}{text}"
                    rf"{{\1c&H{st['primary']}&}} ")
            else:
                parts.append(rf"{{\kf{k_cs}}}{text} ")
        text_line = "".join(parts).strip()
        lines.append(
            f"Dialogue: 0,{_fmt_ts(c_start)},{_fmt_ts(c_end)},Cap,,0,0,0,,{text_line}"
        )

    return (header + "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n" + "\n".join(lines) + "\n")
