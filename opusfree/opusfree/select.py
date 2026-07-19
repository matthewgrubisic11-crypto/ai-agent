"""Pick the most clip-worthy moments and assign a 0-100 virality score.

Opus Clip's scorer is a proprietary model trained on private data; we can't
reproduce that exactly. This is a transparent, deterministic factor system --
every point a clip earns or loses is named in clip.breakdown, so you can see
exactly why a clip scored what it did (and tune the weights below).

Two-stage scoring:
1. Raw factor score: hooks, story/payoff cues, emotion, questions, numbers,
   completeness, length sweet spot, minus penalties for mid-thought starts
   and slow patches.
2. Calibration: raw scores are blended with the clip's rank inside THIS video,
   so your best picks land ~70-95 with meaningful spread. The number ranks
   clips against each other; it is not a guarantee of virality (no score is,
   including Opus's).

With Ollama installed (https://ollama.com) a local LLM re-ranks the shortlist
for a genuinely smarter read of what's interesting -- see llm.py.
"""

from __future__ import annotations

import re
from typing import List

from .models import Clip, Transcript, Word

# ---- Lexicons (edit freely; these are the whole "model") -------------------

HOOK_WORDS = {
    "how", "why", "what", "when", "who", "secret", "never", "always",
    "everyone", "nobody", "biggest", "worst", "best", "most", "stop",
    "listen", "imagine", "truth", "mistake", "mistakes", "warning", "crazy",
    "insane", "shocking", "unbelievable", "hack", "trick", "tip", "tips",
    "lesson", "story", "problem", "here's", "reason", "actually", "honestly",
    "wrong", "right", "changed", "million", "billion", "money", "free",
    "first", "last", "you", "your", "nobody's", "everybody",
}

EMOTION_WORDS = {
    "love", "hate", "amazing", "terrible", "incredible", "awful", "fear",
    "scared", "excited", "angry", "happy", "sad", "surprised", "wow",
    "shocked", "hard", "easy", "powerful", "dangerous", "important", "huge",
    "massive", "beautiful", "brutal", "obsessed", "passion", "proud", "hurt",
    "win", "lose", "won", "lost", "failure", "success", "dream", "dreams",
}

# Story / payoff cues: phrases that signal a narrative arc or an insight
# being delivered -- the moments interviews are watched for.
STORY_CUES = (
    "the reason", "that's when", "that's why", "turns out", "i realized",
    "i learned", "what i learned", "the key", "the secret", "the truth is",
    "one day", "at that point", "and then", "the moment", "i remember",
    "changed my", "changed everything", "taught me", "the difference",
    "most people", "people don't", "nobody talks", "here's the thing",
    "let me tell", "true story", "growing up", "when i was",
)

# Starting a clip on one of these means we're mid-thought -- bad hook.
BAD_START = {
    "and", "but", "so", "because", "which", "also", "then", "like", "yeah",
    "okay", "ok", "um", "uh", "right", "well", "or", "plus", "obviously",
    "basically", "anyway", "though",
}


def _sentence_starts(words: List[Word]) -> List[int]:
    starts = [0]
    for i in range(1, len(words)):
        prev = words[i - 1].text
        if prev and prev[-1] in ".!?":
            starts.append(i)
    return starts


def _build_candidates(transcript: Transcript, min_dur: float, max_dur: float,
                      stride: float) -> List[Clip]:
    words = transcript.words
    if not words:
        return []
    starts = _sentence_starts(words)
    candidates: List[Clip] = []
    last_start_time = -1e9

    for si in starts:
        s_time = words[si].start
        if s_time - last_start_time < stride:
            continue
        chosen: List[Word] | None = None
        for j in range(si + 1, len(words) + 1):
            dur = words[j - 1].end - s_time
            if dur < min_dur:
                continue
            if dur > max_dur:
                break
            ends_sentence = words[j - 1].text[-1:] in ".!?"
            chosen = words[si:j]
            if ends_sentence:
                break
        if chosen:
            candidates.append(Clip(start=chosen[0].start, end=chosen[-1].end,
                                   words=list(chosen)))
            last_start_time = s_time

    return candidates


def _score(clip: Clip) -> None:
    """Assign clip.score plus named reasons and a point-by-point breakdown."""
    tokens = [w.text.lower().strip(".,!?;:\"'") for w in clip.words]
    if not tokens:
        clip.score = 0
        return

    reasons: List[str] = []
    breakdown: List[str] = []
    score = 38.0
    breakdown.append("baseline: +38")

    def add(pts: float, label: str, reason: str | None = None) -> None:
        nonlocal score
        score += pts
        breakdown.append(f"{label}: {pts:+.0f}")
        if reason:
            reasons.append(reason)

    text_lower = " ".join(tokens)
    opener_tokens = tokens[:6]

    # -- Opening hook ---------------------------------------------------------
    if opener_tokens and opener_tokens[0] in BAD_START:
        add(-10, "starts mid-thought")
    if any(t in HOOK_WORDS for t in opener_tokens):
        add(16, "hook in first 6 words", "strong opening hook")
    if any(t in ("how", "why", "what") for t in opener_tokens):
        add(5, "curiosity opener")

    # -- Content signals ------------------------------------------------------
    hook_hits = sum(1 for t in tokens if t in HOOK_WORDS)
    if hook_hits:
        add(min(hook_hits, 6) * 2.0, f"hook words x{min(hook_hits, 6)}")
        if hook_hits >= 3:
            reasons.append("hook-heavy language")

    emo_hits = sum(1 for t in tokens if t in EMOTION_WORDS)
    if emo_hits:
        add(min(emo_hits, 5) * 2.0, f"emotional words x{min(emo_hits, 5)}")
        if emo_hits >= 2:
            reasons.append("emotional language")

    story_hits = sum(1 for cue in STORY_CUES if cue in text_lower)
    if story_hits:
        add(min(story_hits, 3) * 6.0, f"story/payoff cues x{min(story_hits, 3)}",
            "story arc / insight payoff")

    raw_text = clip.text
    if "?" in raw_text:
        add(6, "poses a question", "poses a question")
    if re.search(r"\d", raw_text):
        add(4, "numbers/specifics", "uses numbers/specifics")

    # -- Shape ----------------------------------------------------------------
    d = clip.duration
    if 18 <= d <= 45:
        add(8, "ideal length 18-45s", "ideal length")
    elif d < 12 or d > 70:
        add(-12, "awkward length")

    if clip.words[-1].text[-1:] in ".!?":
        add(5, "ends on a complete sentence", "self-contained")

    wps = len(tokens) / max(d, 1e-6)
    if wps < 1.0:
        add(-8, "slow / sparse speech")
    elif wps > 4.5:
        add(-4, "rushed speech")

    clip.score = int(max(1, min(100, round(score))))
    clip.breakdown = breakdown

    raw = " ".join(w.text for w in clip.words[:8])
    clip.title = re.sub(r"\s+", " ", raw).strip().rstrip(".,;:")
    clip.reasons = reasons


def _calibrate(ranked: List[Clip]) -> None:
    """Blend raw scores with in-video rank so top picks read 70-95.

    The *order* never changes -- this only maps the numbers onto a scale
    where your best-of-video sits high with meaningful spread, instead of
    everything clustering in the 50s-60s.
    """
    n = len(ranked)
    if n == 0:
        return
    for rank, c in enumerate(ranked):
        pct = 1.0 - (rank / max(n - 1, 1))
        mapped = 52 + 43 * (pct ** 1.4)
        c.score = int(max(1, min(97, round(0.4 * c.score + 0.6 * mapped))))
    # Guarantee strictly non-increasing scores in rank order.
    for i in range(1, n):
        if ranked[i].score > ranked[i - 1].score:
            ranked[i].score = ranked[i - 1].score


def _dedupe(clips: List[Clip], min_gap: float) -> List[Clip]:
    kept: List[Clip] = []
    for c in sorted(clips, key=lambda x: x.score, reverse=True):
        if all(abs(c.start - k.start) >= min_gap and
               not (c.start < k.end and c.end > k.start) for k in kept):
            kept.append(c)
    return kept


def select_clips(transcript: Transcript, count: int = 10, min_dur: float = 15.0,
                 max_dur: float = 60.0, use_llm: str | None = None) -> List[Clip]:
    """Return the top ``count`` clips, highest virality score first."""
    candidates = _build_candidates(transcript, min_dur, max_dur, stride=8.0)
    for c in candidates:
        _score(c)

    if use_llm == "ollama":
        from .llm import rerank_with_ollama
        candidates = rerank_with_ollama(candidates)

    ranked = _dedupe(candidates, min_gap=max(min_dur * 0.5, 8.0))
    ranked.sort(key=lambda c: c.score, reverse=True)
    ranked = ranked[:count]
    _calibrate(ranked)
    return ranked


def _prompt_relevance(clip: Clip, terms: List[str]) -> float:
    if not terms:
        return 0.0
    text = " " + clip.text.lower() + " "
    hits = 0
    total_occurrences = 0
    for t in terms:
        occ = text.count(" " + t)
        if occ:
            hits += 1
            total_occurrences += occ
    coverage = hits / len(terms)
    density = min(total_occurrences, 6) / 6.0
    return 0.7 * coverage + 0.3 * density


def select_by_prompt(transcript: Transcript, prompt: str, count: int = 10,
                     min_dur: float = 15.0, max_dur: float = 60.0,
                     use_llm: str | None = None) -> List[Clip]:
    """ClipAnything-style: clips most relevant to a natural-language prompt."""
    candidates = _build_candidates(transcript, min_dur, max_dur, stride=6.0)
    for c in candidates:
        _score(c)

    generic = _is_generic_prompt(prompt)
    if generic:
        # "find the viral/best parts" isn't a topic filter -- it's exactly what
        # the virality scorer already does. Use it directly.
        pass
    elif use_llm == "ollama":
        from .llm import score_relevance_with_ollama
        score_relevance_with_ollama(candidates, prompt)
        for c in candidates:
            rel = getattr(c, "_relevance", 0.0)
            c.score = int(max(1, min(100, round(rel * 70 + c.score * 0.3))))
            if rel > 0:
                c.reasons = [f"matches prompt: {prompt!r}"] + c.reasons
    else:
        terms = [w for w in re.findall(r"[a-zA-Z']+", prompt.lower())
                 if len(w) > 2 and w not in _GENERIC_TERMS]
        for c in candidates:
            rel = _prompt_relevance(c, terms)
            c.score = int(max(1, min(100, round(rel * 80 + c.score * 0.2))))
            if rel > 0:
                c.reasons = [f"matches prompt: {prompt!r}"] + c.reasons

    ranked = _dedupe(candidates, min_gap=max(min_dur * 0.5, 6.0))
    if not generic:
        ranked = [c for c in ranked if c.score > 20]
    ranked.sort(key=lambda c: c.score, reverse=True)
    ranked = ranked[:count]
    _calibrate(ranked)
    return ranked


# Prompts like "find the most viral parts" carry no topic terms; treat them as
# plain virality ranking instead of matching the words "viral"/"best" etc.
_GENERIC_TERMS = {
    "find", "make", "give", "pull", "get", "turn", "create", "curate",
    "most", "best", "top", "good", "great", "viral", "virality", "clip",
    "clips", "video", "videos", "reel", "reels", "short", "shorts",
    "moment", "moments", "part", "parts", "entertaining", "interesting",
    "important", "material", "possible", "possibile", "them", "with", "the",
    "and", "that", "into", "every", "all",
}


def _is_generic_prompt(prompt: str) -> bool:
    terms = [w for w in re.findall(r"[a-zA-Z']+", prompt.lower()) if len(w) > 2]
    return all(t in _GENERIC_TERMS for t in terms) if terms else True
