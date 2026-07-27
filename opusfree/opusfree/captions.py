"""Kinetic, retention-first captions as ASS subtitles.

Spec-aligned engine:
- <=3 words per screen (long lines kill vertical retention)
- centered in the 9:16 safe zone, heavy-stroke high-contrast sans
- karaoke highlight on the spoken word + pop-in per phrase
- SEMANTIC color: money/profit -> green, danger/mistake -> red, plus a
  configurable accent for other power words; optional fire emoji on
  high-energy words.

Rendering is ffmpeg/libass in render.py.
"""

from __future__ import annotations

from typing import List

from .models import Word

# Semantic color map (ASS uses &HBBGGRR, i.e. reversed hex of an #RRGGBB).
COLOR_GREEN = "55C522"          # money / profit / growth (#22C55E)
COLOR_RED = "3333EF"            # danger / mistake / loss  (#EF3333)

MONEY_WORDS = {
    "money", "cash", "profit", "profits", "rich", "wealth", "wealthy",
    "millionaire", "billionaire", "million", "billion", "dollars", "revenue",
    "income", "paid", "pay", "salary", "fortune", "roi", "growth", "win",
    "won", "success", "free",
}
DANGER_WORDS = {
    "danger", "dangerous", "mistake", "mistakes", "wrong", "fail", "failure",
    "failed", "lose", "lost", "loss", "death", "die", "kill", "worst", "never",
    "warning", "trap", "broke", "debt", "risk", "hurt", "pain", "scared",
    "fear", "crash", "hate",
}
HIGH_ENERGY = {
    "insane", "crazy", "unbelievable", "shocking", "wild", "huge", "massive",
    "incredible", "amazing", "explode", "exploded", "fire", "unreal", "boom",
    "biggest", "greatest",
}
POWER_WORDS = MONEY_WORDS | DANGER_WORDS | HIGH_ENERGY | {
    "secret", "truth", "everyone", "nobody", "always", "most", "first",
    "last", "important", "powerful", "changed", "love",
}

STYLES = {
    # Clean, modern, high-retention: 2 words at a time, active word highlighted.
    "retention": {
        "font": "Arial Black", "size_frac": 0.050, "margin_frac": 0.34,
        "primary": "FFFFFF", "highlight": "00E9FF", "accent": "00E9FF",
        "outline": "000000", "outline_w": 4, "shadow": 1,
        "uppercase": True, "max_words": 2, "max_dur": 1.2, "pop": True,
        "emoji": False,
    },
    "clean-white": {
        "font": "Arial", "size_frac": 0.040, "margin_frac": 0.26,
        "primary": "FFFFFF", "highlight": "00D7FF", "accent": "00D7FF",
        "outline": "202020", "outline_w": 3, "shadow": 1,
        "uppercase": False, "max_words": 3, "max_dur": 2.0, "pop": False,
        "emoji": False,
    },
    "bold-yellow": {
        "font": "Arial Black", "size_frac": 0.046, "margin_frac": 0.24,
        "primary": "FFFFFF", "highlight": "00F0FF", "accent": "00F0FF",
        "outline": "000000", "outline_w": 4, "shadow": 1,
        "uppercase": True, "max_words": 3, "max_dur": 1.8, "pop": True,
        "emoji": False,
    },
    "hormozi": {
        "font": "Arial Black", "size_frac": 0.055, "margin_frac": 0.30,
        "primary": "FFFFFF", "highlight": "00FF00", "accent": "00FF00",
        "outline": "000000", "outline_w": 6, "shadow": 2,
        "uppercase": True, "max_words": 3, "max_dur": 1.6, "pop": True,
        "emoji": True,
    },
}


def word_color(bare: str, style: dict) -> str | None:
    """Semantic color for a word, or None for default."""
    if bare in MONEY_WORDS or bare.rstrip("%$kmb").isdigit():
        return COLOR_GREEN
    if bare in DANGER_WORDS:
        return COLOR_RED
    if bare in POWER_WORDS:
        return style["accent"]
    return None


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
              style_name: str = "retention", emoji: bool | None = None) -> str:
    """Return ASS subtitle text. ``words`` should already be clip-relative if
    they came from a tightened EDL; otherwise clip_start is subtracted."""
    st = STYLES.get(style_name, STYLES["retention"])
    use_emoji = st["emoji"] if emoji is None else emoji
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

    pop_tag = (r"{\fscx82\fscy82\t(0,110,\fscx100\fscy100)}"
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
            if use_emoji and bare in HIGH_ENERGY:
                text += " \U0001F525"  # fire
            col = word_color(bare, st)
            if col:
                parts.append(rf"{{\kf{k_cs}\1c&H{col}&}}{text}"
                             rf"{{\1c&H{st['primary']}&}} ")
            else:
                parts.append(rf"{{\kf{k_cs}}}{text} ")
        lines.append(f"Dialogue: 0,{_fmt_ts(c_start)},{_fmt_ts(c_end)},"
                     f"Cap,,0,0,0,,{''.join(parts).strip()}")

    return (header + "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n" + "\n".join(lines) + "\n")
