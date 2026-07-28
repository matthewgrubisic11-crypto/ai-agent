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

# Research (Berger & Milkman): HIGH-arousal emotion drives sharing; low-arousal
# (sadness/calm) suppresses it. Score by arousal, not just positive/negative.
AROUSAL_HIGH = {
    # awe
    "incredible", "unbelievable", "insane", "mind-blowing", "amazing", "stunning",
    "genius", "legendary", "unreal", "wild", "epic", "phenomenal",
    # anger / outrage
    "outrageous", "furious", "disgusting", "ridiculous", "scam", "lie", "lied",
    "corrupt", "betrayed", "unfair", "rigged", "exposed", "worst",
    # anxiety / fear
    "terrifying", "scared", "dangerous", "warning", "risk", "threat", "crisis",
    "shocking", "nightmare", "panic", "desperate", "afraid",
    # amusement
    "hilarious", "funny", "laugh", "crazy", "ridiculous", "absurd", "savage",
}
AROUSAL_LOW = {  # deactivating -> suppresses sharing
    "sad", "boring", "tired", "calm", "peaceful", "fine", "okay", "content",
    "relaxed", "sleepy", "dull", "meh", "whatever", "eventually",
}
# Social currency: sharing it makes the SHARER look smart/in-the-know.
SOCIAL_CURRENCY = (
    "most people don't", "nobody talks about", "nobody tells you",
    "you won't believe", "secret", "hidden", "insider", "the truth about",
    "what they don't", "little known", "the real reason", "trick", "hack",
    "before it's too late", "you're doing it wrong", "stop doing",
)

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

# Greetings / intros that must never open a clip (spec negative constraint).
GREETING_START = {
    "hi", "hey", "hello", "welcome", "thanks", "thank", "today", "alright",
    "guys", "everybody", "everyone's", "morning", "afternoon",
}

# Consensus-breaking: challenges common knowledge.
CONSENSUS_CUES = (
    "most people", "everyone thinks", "people think", "nobody talks",
    "nobody tells", "the truth is", "contrary to", "actually", "myth",
    "wrong about", "you've been", "they lied", "don't believe", "the opposite",
    "isn't what", "not what you", "common", "unpopular", "hot take",
)
# Emotional vulnerability: raw personal truth.
VULNERABILITY_CUES = (
    "i was scared", "i cried", "i failed", "i almost", "i hit rock",
    "i struggled", "i remember", "i felt", "the hardest", "i lost", "my dad",
    "my mom", "my father", "my mother", "when i was", "growing up", "i nearly",
    "broke down", "i couldn't", "honestly", "i'll be honest", "truth be told",
)
# High utility: actionable advice.
UTILITY_CUES = (
    "you should", "you need to", "the key is", "here's how", "the trick is",
    "start by", "step one", "the first thing", "what you do is", "all you have",
    "make sure", "never", "always", "the secret", "do this", "try this",
    "the best way", "focus on", "stop doing",
)
# Payoff / resolution cues near the end (spec requires a definitive payoff).
PAYOFF_CUES = (
    "that's why", "that's the", "so the", "the point is", "the lesson",
    "and that's how", "in the end", "bottom line", "so if you", "that's what",
    "which is why", "the moral", "remember that", "never forget", "so do",
    "and that changed", "it's that simple", "that's it", "the difference",
)


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

    # -- Arousal (Berger & Milkman: HIGH arousal drives shares) --------------
    high_ar = sum(1 for t in tokens if t in AROUSAL_HIGH)
    low_ar = sum(1 for t in tokens if t in AROUSAL_LOW)
    if high_ar:
        add(min(high_ar, 5) * 3.0, f"high-arousal x{min(high_ar, 5)}",
            "high-arousal emotion (awe/anger/anxiety/amusement)")
    if low_ar:
        add(-min(low_ar, 4) * 3.0, f"low-arousal x{min(low_ar, 4)}")

    # -- Shareability / social currency (makes the sharer look in-the-know) ---
    share_hits = sum(1 for c in SOCIAL_CURRENCY if c in text_lower)
    if share_hits:
        add(min(share_hits, 3) * 5.0, f"social currency x{min(share_hits, 3)}",
            "shareable (status/insider value)")

    # -- 0-3s hook (research: first-3-seconds is THE retention signal) --------
    first3_tok = [w.text.lower().strip(".,!?;:\"'")
                  for w in clip.words if w.start - clip.start <= 3.0]
    hook3 = (any(t in HOOK_WORDS or t in AROUSAL_HIGH for t in first3_tok)
             or "?" in " ".join(first3_tok))
    if hook3:
        add(14, "strong 0-3s hook", "hook lands in first 3s")
    else:
        add(-8, "weak 0-3s hook")

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

    # -- Narrative-arc sub-scores (spec Step 2 matrix, 0-10 each) ------------
    n_words = len(clip.words)
    head = " ".join(tokens[:max(6, n_words // 3)])
    tail = " ".join(tokens[-(max(6, n_words // 3)):])

    consensus = min(10, 3 + 4 * sum(c in text_lower for c in CONSENSUS_CUES))
    vulner = min(10, 2 + 4 * sum(c in text_lower for c in VULNERABILITY_CUES))
    utility = min(10, 2 + 3 * sum(c in text_lower for c in UTILITY_CUES))

    has_hook = (opener_tokens and opener_tokens[0] not in BAD_START
                and opener_tokens[0] not in GREETING_START
                and (any(t in HOOK_WORDS for t in opener_tokens) or "?" in head))
    has_payoff = (any(c in tail for c in PAYOFF_CUES)
                  or clip.words[-1].text[-1:] in ".!?")
    arc = (4 if has_hook else 0) + (4 if has_payoff else 0) + (
        2 if 20 <= d <= 60 else 0)

    arousal = min(10, 2 + 2 * high_ar - 2 * low_ar)
    shareability = min(10, 2 + 3 * share_hits + (2 if hook3 else 0))
    clip.subscores = {"hook_0_3s": 10 if hook3 else 3,
                      "arousal": max(0, arousal),
                      "shareability": max(0, shareability),
                      "consensus_breaking": consensus,
                      "emotional_vulnerability": vulner,
                      "high_utility": utility, "narrative_arc": arc}
    clip.has_payoff = has_payoff
    if consensus >= 6:
        add(6, "challenges consensus", "consensus-breaking")
    if vulner >= 6:
        add(6, "raw personal truth", "emotional vulnerability")
    if utility >= 6:
        add(5, "actionable advice", "high utility")
    if has_payoff:
        add(4, "clear payoff", "definitive payoff")
    else:
        add(-14, "no clear payoff")

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
    for c in ranked:
        c.viral_score = round(c.score / 10.0, 1)
        c.justification = _justify(c)


def _justify(clip: Clip) -> str:
    """One-line, spec-style reason this clip should perform."""
    ss = clip.subscores or {}
    bits = []
    if ss.get("consensus_breaking", 0) >= 6:
        bits.append("challenges what most people believe")
    if ss.get("emotional_vulnerability", 0) >= 6:
        bits.append("shares a raw personal moment")
    if ss.get("high_utility", 0) >= 6:
        bits.append("delivers immediately usable advice")
    if clip.has_payoff:
        bits.append("lands on a clear payoff")
    else:
        bits.append("carries momentum from a strong hook")
    lead = "Strong hook" if clip.reasons and "hook" in " ".join(clip.reasons) \
        else "Self-contained moment"
    return f"{lead} that {', and '.join(bits) or 'holds attention'}."


def _dedupe(clips: List[Clip], min_gap: float) -> List[Clip]:
    kept: List[Clip] = []
    for c in sorted(clips, key=lambda x: x.score, reverse=True):
        if all(abs(c.start - k.start) >= min_gap and
               not (c.start < k.end and c.end > k.start) for k in kept):
            kept.append(c)
    return kept


def _passes_constraints(clip: Clip, strict: bool) -> bool:
    """Enforce the spec's hard negative constraints on a clip."""
    toks = [w.text.lower().strip(".,!?;:\"'") for w in clip.words]
    if not toks:
        return False
    if toks[0] in GREETING_START or toks[0] in BAD_START:
        return False           # never open on a greeting / filler
    if strict and not clip.has_payoff:
        return False           # never ship an unresolved clip
    return True


def select_clips(transcript: Transcript, count: int = 10, min_dur: float = 15.0,
                 max_dur: float = 60.0, use_llm: str | None = None,
                 strict_arc: bool = True) -> List[Clip]:
    """Return the top ``count`` clips, highest virality score first."""
    candidates = _build_candidates(transcript, min_dur, max_dur, stride=8.0)
    for c in candidates:
        _score(c)

    candidates = [c for c in candidates if _passes_constraints(c, strict_arc)]

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

    candidates = [c for c in candidates if _passes_constraints(c, False)]
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
