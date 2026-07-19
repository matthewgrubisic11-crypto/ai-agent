"""Generate animated word-by-word captions as an ASS subtitle file.

Groups words into short phrases and uses ASS karaoke tags so the current word
highlights as it's spoken (the burned-in style Opus/TikTok clips use).
Rendering is done by ffmpeg/libass in render.py.
"""

from __future__ import annotations

from typing import List

from .models import Word

# A few ready-made looks. Colors are ASS &HAABBGGRR (alpha, blue, green, red).
STYLES = {
    "bold-yellow": {
        "font": "Arial Black", "size": 20, "primary": "&H00FFFFFF",
        "highlight": "&H0000F0FF", "outline": "&H00000000", "outline_w": 3,
    },
    "clean-white": {
        "font": "Arial", "size": 18, "primary": "&H00FFFFFF",
        "highlight": "&H0000E0FF", "outline": "&H00202020", "outline_w": 2,
    },
    "hormozi": {
        "font": "Arial Black", "size": 22, "primary": "&H00FFFFFF",
        "highlight": "&H0000FF00", "outline": "&H00000000", "outline_w": 4,
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


def _chunk_words(words: List[Word], max_words: int = 4, max_dur: float = 2.4
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
              style_name: str = "bold-yellow") -> str:
    """Return ASS subtitle text; word times are shifted to clip-relative."""
    style = STYLES.get(style_name, STYLES["bold-yellow"])

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{style['font']},{style['size']},{style['primary']},{style['highlight']},{style['outline']},&H80000000,-1,0,0,0,100,100,0,0,1,{style['outline_w']},1,2,40,40,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = []
    for chunk in _chunk_words(words, ):
        c_start = chunk[0].start - clip_start
        c_end = chunk[-1].end - clip_start
        # Build karaoke text: \k duration (centiseconds) before each word.
        parts = []
        for i, w in enumerate(chunk):
            nxt = chunk[i + 1].start if i + 1 < len(chunk) else w.end
            k_cs = max(1, int(round((nxt - w.start) * 100)))
            safe = w.text.replace("{", "(").replace("}", ")")
            parts.append(f"{{\\kf{k_cs}}}{safe} ")
        text = "".join(parts).strip()
        lines.append(
            f"Dialogue: 0,{_fmt_ts(c_start)},{_fmt_ts(c_end)},Cap,,0,0,0,,{text}"
        )

    return header + "\n".join(lines) + "\n"
