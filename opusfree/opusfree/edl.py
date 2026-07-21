"""Surgical transcript editing: build a clean-cut EDL and a tightened timeline.

Removes filler words and dead air (>0.2s gaps), then restitches the kept words
into a tight, high-energy timeline. Returns both the human/JSON-facing EDL
(keep/delete per word) and the machine-facing source spans + remapped words
that render.py uses to actually cut and re-caption the clip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .models import Word

FILLER = {
    "um", "uh", "erm", "hmm", "mm", "uhh", "umm", "eh", "ah", "like",
    "y'know", "basically", "literally", "actually", "honestly",
}
# Multi-word fillers handled as sequences.
FILLER_PHRASES = (("you", "know"), ("i", "mean"), ("sort", "of"),
                  ("kind", "of"), ("you", "know", "what", "i", "mean"))

MAX_GAP = 0.2   # dead air longer than this is cut


@dataclass
class EDLEntry:
    word: str
    start: float
    end: float
    action: str  # "keep" | "delete"


@dataclass
class TightPlan:
    edl: List[EDLEntry]
    spans: List[Tuple[float, float]]      # source time spans to keep, in order
    words: List[Word]                     # kept words, times remapped to output
    removed: float = 0.0                  # seconds trimmed out


def _mark_fillers(words: List[Word]) -> List[bool]:
    """True at indices to delete as filler."""
    n = len(words)
    delete = [False] * n
    lows = [w.text.lower().strip(".,!?;:\"'") for w in words]
    for i, low in enumerate(lows):
        if low in FILLER:
            delete[i] = True
    for phrase in FILLER_PHRASES:
        L = len(phrase)
        for i in range(n - L + 1):
            if tuple(lows[i:i + L]) == phrase:
                for j in range(i, i + L):
                    delete[j] = True
    # Stutters: "I- I", "the the" repeats
    for i in range(1, n):
        if lows[i] and lows[i] == lows[i - 1] and len(lows[i]) <= 4:
            delete[i - 1] = True
    return delete


def build_plan(words: List[Word], clip_start: float, tighten: bool = True
               ) -> TightPlan:
    """Create the EDL + tightened timeline for one clip's words."""
    if not words:
        return TightPlan(edl=[], spans=[], words=[])

    delete = _mark_fillers(words) if tighten else [False] * len(words)

    edl = [EDLEntry(w.text, round(w.start - clip_start, 3),
                    round(w.end - clip_start, 3),
                    "delete" if delete[i] else "keep")
           for i, w in enumerate(words)]

    if not tighten:
        remapped = [Word(w.text, round(w.start - clip_start, 3),
                         round(w.end - clip_start, 3)) for w in words]
        return TightPlan(edl=edl,
                         spans=[(words[0].start, words[-1].end)],
                         words=remapped, removed=0.0)

    # Kept source spans: contiguous runs of kept words, but also cut any
    # inter-word gap longer than MAX_GAP even between two kept words.
    spans: List[Tuple[float, float]] = []
    remapped: List[Word] = []
    out_t = 0.0
    prev_end = None
    cur_start = None

    for i, w in enumerate(words):
        if delete[i]:
            if cur_start is not None:
                spans.append((cur_start, prev_end))
                cur_start = None
            continue
        if cur_start is None:
            cur_start = w.start
        elif w.start - prev_end > MAX_GAP:
            # close previous span, open a new one (dead air removed)
            spans.append((cur_start, prev_end))
            cur_start = w.start
        prev_end = w.end

    if cur_start is not None:
        spans.append((cur_start, prev_end))

    # Remap kept words onto the tightened timeline.
    span_idx = 0
    out_t = 0.0
    for (s, e) in spans:
        for w in words:
            if w.start >= s - 1e-6 and w.end <= e + 1e-6:
                dur = w.end - w.start
                ns = out_t + (w.start - s)
                remapped.append(Word(w.text, round(ns, 3), round(ns + dur, 3)))
        out_t += (e - s)

    total_src = words[-1].end - words[0].start
    removed = total_src - sum(e - s for s, e in spans)
    return TightPlan(edl=edl, spans=spans, words=remapped,
                     removed=round(removed, 3))
