"""Kinetic caption engine with a Submagic-style preset library.

Word-by-word active-word highlight (2.3x completion in A/B tests) rendered as
ASS/libass. Presets vary font, size, color, position, words-per-screen, pop
animation, and border style -- including the signature "highlight box" look
(opaque box behind the active words, BorderStyle=3).

Semantic color still applies inside every style: money/profit -> green,
danger/mistake -> red.
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

# --- Preset library -------------------------------------------------------
# border_style: 1 = outline+shadow, 3 = opaque box behind text (the box look)
# box_color:    used when border_style==3 (the box fill), ASS BBGGRR
_BASE = {
    "size_frac": 0.050, "margin_frac": 0.34, "primary": "FFFFFF",
    "highlight": "00E9FF", "accent": "00E9FF", "outline": "000000",
    "outline_w": 4, "shadow": 1, "uppercase": True, "max_words": 2,
    "max_dur": 1.2, "pop": True, "emoji": False, "border_style": 1,
    "box_color": "000000", "font": "Arial Black",
}


def _style(**over):
    s = dict(_BASE)
    s.update(over)
    return s


STYLES = {
    # clean modern default
    "retention": _style(),
    # one word at a time, big
    "word-pop": _style(max_words=1, size_frac=0.060, highlight="00E9FF"),
    # Hormozi green, all caps, punchy
    "hormozi": _style(highlight="00FF00", accent="00FF00", outline_w=5,
                      size_frac=0.055),
    # MrBeast-ish thick bold, red highlight
    "beast": _style(highlight="3333EF", accent="3333EF", size_frac=0.058,
                    outline_w=6),
    # TikTok classic white with yellow karaoke
    "tiktok": _style(highlight="00F0FF", accent="00F0FF", uppercase=False,
                     size_frac=0.044, outline_w=3),
    # opaque yellow box, black text (Submagic signature)
    "box-yellow": _style(border_style=3, box_color="20E0FF", primary="000000",
                         highlight="000000", accent="000000", outline_w=1,
                         shadow=0, size_frac=0.046),
    # opaque black box, white text with yellow active word
    "box-black": _style(border_style=3, box_color="000000", primary="FFFFFF",
                        highlight="20E0FF", accent="20E0FF", outline_w=1,
                        shadow=0, size_frac=0.046),
    # green opaque box
    "box-green": _style(border_style=3, box_color="55C522", primary="FFFFFF",
                        highlight="FFFFFF", accent="FFFFFF", outline_w=1,
                        shadow=0, size_frac=0.046),
    # neon cyan glow
    "neon": _style(primary="F5FFFF", highlight="FFF000", accent="FFF000",
                   outline="AA6600", outline_w=3, shadow=3),
    # minimal clean lowercase, small, bottom-third
    "minimal": _style(uppercase=False, size_frac=0.036, margin_frac=0.20,
                      outline_w=2, pop=False, highlight="FFFFFF",
                      accent="FFFFFF", font="Arial"),
    # bold white, no color (subtle)
    "clean-white": _style(highlight="FFFFFF", accent="FFFFFF", uppercase=False,
                          size_frac=0.042, outline_w=3, pop=False, font="Arial"),
    # classic bold yellow karaoke
    "bold-yellow": _style(highlight="00F0FF", accent="00F0FF", max_words=3,
                          size_frac=0.046),
}


def word_color(bare: str, style: dict) -> str | None:
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


def _wrap_title(text: str, per_line: int = 22) -> str:
    """Wrap a hook title into <=2 lines for the top overlay."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > per_line and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return r"\N".join(lines[:2])


def build_ass(words: List[Word], clip_start: float, video_w: int, video_h: int,
              style_name: str = "retention", emoji: bool | None = None,
              hook_title: str | None = None, hook_secs: float = 2.6) -> str:
    """Return ASS subtitle text. ``words`` should already be clip-relative.

    If ``hook_title`` is given, a bold title card is shown at the top for the
    first ``hook_secs`` seconds (Submagic-style hook overlay)."""
    st = STYLES.get(style_name, STYLES["retention"])
    use_emoji = st["emoji"] if emoji is None else emoji
    size = max(28, int(video_h * st["size_frac"]))
    margin_v = int(video_h * st["margin_frac"])
    title_size = max(30, int(video_h * 0.030))
    # For the opaque-box style the OutlineColour is the box fill.
    outline_col = st["box_color"] if st["border_style"] == 3 else st["outline"]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{st['font']},{size},&H00{st['primary']},&H00{st['highlight']},&H00{outline_col},&H80000000,-1,0,0,0,100,100,0,0,{st['border_style']},{st['outline_w']},{st['shadow']},2,60,60,{margin_v},1
Style: Hook,Arial Black,{title_size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,3,6,0,8,80,80,{int(video_h*0.06)},1
"""

    pop_tag = (r"{\fscx80\fscy80\t(0,110,\fscx100\fscy100)}"
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
                text += " \U0001F525"
            col = word_color(bare, st)
            if col:
                parts.append(rf"{{\kf{k_cs}\1c&H{col}&}}{text}"
                             rf"{{\1c&H{st['primary']}&}} ")
            else:
                parts.append(rf"{{\kf{k_cs}}}{text} ")
        lines.append(f"Dialogue: 0,{_fmt_ts(c_start)},{_fmt_ts(c_end)},"
                     f"Cap,,0,0,0,,{''.join(parts).strip()}")

    if hook_title:
        title = _wrap_title(hook_title.strip().upper())
        fade = r"{\fad(150,200)}"
        lines.insert(0, f"Dialogue: 1,{_fmt_ts(0)},{_fmt_ts(hook_secs)},"
                        f"Hook,,0,0,0,,{fade}{title}")

    return (header + "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n" + "\n".join(lines) + "\n")
