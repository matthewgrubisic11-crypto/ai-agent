"""Generate the per-clip 'growth kit' and the visual/audio directive list.

Produces the JSON structures the spec asks for: visual_directives (a
zoom/caption/B-roll cue roughly every 1.5-2s, with jump cuts masked), a
b-roll query per abstract keyword, audio_directives, on-screen title hooks,
an SEO caption (hook / debate question / 5 hashtags), and the thumbnail time.

B-roll queries and the music track_style are *directives* (text): fetching
licensed stock footage/music needs external paid libraries, so opusfree emits
the instructions and (optionally) fetches b-roll only if a Pexels key is set.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import List

from .captions import HIGH_ENERGY, word_color, STYLES
from .models import Clip, Word

# Concrete, visualisable nouns worth a B-roll cutaway (abstract->query).
BROLL_HINTS = {
    "money": "cash counting close up", "business": "modern office team",
    "city": "aerial city skyline timelapse", "phone": "smartphone screen macro",
    "computer": "code on screen matrix", "gym": "intense gym workout",
    "car": "luxury car driving", "food": "gourmet food plating",
    "brain": "glowing brain neural network", "time": "fast clock timelapse",
    "money's": "cash counting close up", "market": "stock market ticker",
    "ocean": "ocean waves aerial", "space": "planets in space",
    "team": "startup team collaborating", "win": "athlete winning celebration",
}

TITLE_TEMPLATES = [
    "The Truth About {kw} Nobody Tells You",
    "Why {kw} Changes Everything",
    "This {kw} Advice Will Blow Your Mind",
    "What Everyone Gets Wrong About {kw}",
    "The {kw} Secret They Don't Want You To Know",
]

DEBATE_QUESTIONS = [
    "Do you actually agree with this? 👇",
    "Hot take or facts? Let me know below.",
    "Is this the best advice you've heard or totally wrong?",
    "Would you have the guts to do this?",
    "Am I the only one who needed to hear this?",
]

_STOP = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for",
         "with", "is", "are", "was", "were", "be", "it", "this", "that",
         "these", "those", "you", "your", "i", "we", "they", "he", "she",
         "so", "just", "like", "about", "what", "when", "how", "why", "not",
         "do", "does", "did", "have", "has", "will", "would", "can", "could",
         "get", "got", "going", "gonna", "really", "very", "much", "many",
         "some", "any", "all", "most", "more", "than", "then", "there",
         "here", "one", "two", "every", "single", "people", "think", "know",
         "want", "make", "made", "need", "because", "which", "who", "them",
         "our", "out", "up", "down", "now", "even", "also", "still", "back",
         # filler
         "um", "uh", "erm", "hmm", "eh", "ah", "basically", "literally",
         "actually", "honestly", "mean", "sort", "kind", "yeah", "okay"}


def keywords(text: str, k: int = 6) -> List[str]:
    toks = re.findall(r"[a-zA-Z']+", text.lower())
    counts = Counter(t for t in toks if t not in _STOP and len(t) > 3)
    return [w for w, _ in counts.most_common(k)]


def _fmt_tc(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def visual_directives(words: List[Word], cut_points: List[float],
                      style_name: str, out_dir_start: float = 0.0
                      ) -> List[dict]:
    """A caption+action cue every ~1.5-2s; zoom or B-roll masks each jump cut.

    ``words`` are output-timeline (tightened) words; ``cut_points`` are output
    times where dead air/filler was removed (jump cuts to mask).
    """
    st = STYLES.get(style_name, STYLES["retention"])
    directives: List[dict] = []
    chunk: List[Word] = []
    cuts = sorted(cut_points)

    def flush(nextword_start: float | None):
        if not chunk:
            return
        t0 = chunk[0].start
        text = " ".join(w.text for w in chunk)
        if st["uppercase"]:
            text = text.upper()
        # Does a jump cut fall in/next to this block? If so, mask it.
        masked = any(abs(c - t0) < 0.25 for c in cuts)
        bare_last = chunk[-1].text.lower().strip(".,!?;:\"'")
        broll = None
        for w in chunk:
            b = w.text.lower().strip(".,!?;:\"'")
            if b in BROLL_HINTS:
                broll = BROLL_HINTS[b]
                break
        col = None
        for w in chunk:
            c = word_color(w.text.lower().strip(".,!?;:\"'"), st)
            if c:
                col = "#" + c[4:6] + c[2:4] + c[0:2]  # BBGGRR -> #RRGGBB
                break
        action = ("Overlay B-Roll" if (masked and broll)
                  else "Zoom 112%" if masked
                  else "Zoom 100%")
        d = {"timestamp": _fmt_tc(t0), "action": action,
             "caption": text[:40],
             "caption_color": col or "#FFFFFF"}
        if action == "Overlay B-Roll":
            d["b_roll_query"] = broll
        if bare_last in HIGH_ENERGY:
            d["caption"] += " \U0001F525"
        directives.append(d)

    for w in words:
        if chunk and (len(chunk) >= st["max_words"] or
                      w.start - chunk[0].start > 1.9 or
                      chunk[-1].text[-1:] in ".!?"):
            flush(w.start)
            chunk = []
        chunk.append(w)
    flush(None)
    return directives


def growth_kit(clip: Clip, thumbnail_tc: str, use_llm: str | None = None
               ) -> dict:
    """3 title hooks, an SEO caption, and the thumbnail timestamp."""
    kws = keywords(clip.text)
    topic = (kws[0].title() if kws else "This")

    if use_llm == "ollama":
        from .llm import growth_kit_with_ollama
        llm = growth_kit_with_ollama(clip)
        if llm:
            llm["thumbnail_timestamp"] = thumbnail_tc
            return llm

    titles = [t.format(kw=topic) for t in TITLE_TEMPLATES[:3]]
    # Hook line: first sentence with filler words stripped out.
    from .edl import FILLER
    clean = " ".join(w for w in clip.text.split()
                     if w.lower().strip(".,!?;:\"'") not in FILLER)
    hook = clean.strip().split(".")[0][:80].strip()
    question = DEBATE_QUESTIONS[abs(hash(clip.text)) % len(DEBATE_QUESTIONS)]
    niche = ["#" + re.sub(r"[^a-z0-9]", "", w) for w in kws[:3]]
    broad = ["#fyp", "#viral"]
    hashtags = [h for h in niche + broad if len(h) > 1][:5]
    caption = f"{hook}\n\n{question}\n\n{' '.join(hashtags)}"
    return {"on_screen_titles": titles, "post_caption": caption,
            "thumbnail_timestamp": thumbnail_tc}


def audio_directives(clip: Clip) -> dict:
    """Pick a music mood from the clip's tone and state ducking behavior."""
    text = clip.text.lower()
    if any(w in text for w in ("money", "business", "success", "win", "grind")):
        mood = "Uplifting Modern Beats"
    elif any(w in text for w in ("fear", "danger", "dark", "death", "hard",
                                 "pain", "struggle")):
        mood = "Dark Industrial Synth Tension"
    else:
        mood = "High-Energy Lo-Fi"
    return {"track_style": mood, "dialogue_ducking_db": -4,
            "pause_boost_db": 2, "dialogue_enhanced": True}
