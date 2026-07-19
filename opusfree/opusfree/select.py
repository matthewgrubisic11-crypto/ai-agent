"""Pick the most clip-worthy moments and assign a 0-100 virality score.

Opus Clip's scorer is a proprietary model trained on private data; we can't
reproduce that exactly. Instead we use a transparent, tunable heuristic that
rewards the traits viral shorts actually share: a strong opening hook, a
self-contained arc, emotional/opinionated language, questions, numbers/lists,
and a good length. If you have a local LLM via Ollama, ``--llm ollama`` will
re-rank the shortlist for sharper picks — still fully local and free.
"""

from __future__ import annotations

import re
from typing import List

from .models import Clip, Transcript, Word

# Words/phrases that tend to open or power a viral short.
HOOK_WORDS = {
    "how", "why", "what", "when", "who", "secret", "never", "always", "everyone",
    "nobody", "biggest", "worst", "best", "most", "stop", "listen", "imagine",
    "truth", "mistake", "mistakes", "warning", "crazy", "insane", "shocking",
    "unbelievable", "hack", "trick", "tip", "tips", "lesson", "story", "problem",
    "here's", "reason", "actually", "honestly", "wrong", "right", "changed",
    "million", "billion", "money", "free", "first", "last", "you", "your",
}
EMOTION_WORDS = {
    "love", "hate", "amazing", "terrible", "incredible", "awful", "fear",
    "scared", "excited", "angry", "happy", "sad", "surprised", "wow", "shocked",
    "hard", "easy", "powerful", "dangerous", "important", "huge", "massive",
}


def _sentence_starts(words: List[Word]) -> List[int]:
    """Indices where a new sentence likely begins (good clip cut points)."""
    starts = [0]
    for i in range(1, len(words)):
        prev = words[i - 1].text
        if prev and prev[-1] in ".!?":
            starts.append(i)
    return starts


def _build_candidates(transcript: Transcript, min_dur: float, max_dur: float,
                      stride: float) -> List[Clip]:
    """Generate overlapping candidate clips aligned to sentence boundaries."""
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
        # Extend word-by-word until we're inside the target duration window.
        chosen: List[Word] | None = None
        for j in range(si + 1, len(words) + 1):
            dur = words[j - 1].end - s_time
            if dur < min_dur:
                continue
            if dur > max_dur:
                break
            # Prefer ending on a sentence boundary.
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
    """Assign clip.score (0-100), a title, and human-readable reasons."""
    words = [w.text.lower().strip(".,!?;:\"'") for w in clip.words]
    if not words:
        clip.score = 0
        return

    reasons: List[str] = []
    score = 40.0  # baseline

    opener = " ".join(words[:6])
    if any(h in opener.split() for h in HOOK_WORDS):
        score += 18
        reasons.append("strong opening hook")

    hook_hits = sum(1 for w in words if w in HOOK_WORDS)
    score += min(hook_hits, 6) * 2.5
    if hook_hits >= 3:
        reasons.append("hook-heavy language")

    emo_hits = sum(1 for w in words if w in EMOTION_WORDS)
    score += min(emo_hits, 5) * 2.0
    if emo_hits >= 2:
        reasons.append("emotional language")

    text = clip.text
    if "?" in text:
        score += 6
        reasons.append("poses a question")
    if re.search(r"\d", text):
        score += 5
        reasons.append("uses numbers/specifics")

    # Length sweet spot for shorts: ~18-45s peaks, tails off outside.
    d = clip.duration
    if 18 <= d <= 45:
        score += 8
        reasons.append("ideal length")
    elif d < 12 or d > 70:
        score -= 12

    # Completeness: starts capitalised-ish and ends on punctuation.
    if clip.words[-1].text[-1:] in ".!?":
        score += 5
        reasons.append("self-contained")

    # Penalise very sparse (long pauses) or very dense filler segments.
    wps = len(words) / max(d, 1e-6)
    if wps < 1.0:
        score -= 8
    elif wps > 4.5:
        score -= 4

    clip.score = int(max(1, min(100, round(score))))

    # Title = first ~8 words, cleaned up.
    raw = " ".join(w.text for w in clip.words[:8])
    clip.title = re.sub(r"\s+", " ", raw).strip().rstrip(".,;:")
    clip.reasons = reasons


def _dedupe(clips: List[Clip], min_gap: float) -> List[Clip]:
    """Drop clips that overlap a higher-scoring one (keep variety)."""
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
    return ranked[:count]
