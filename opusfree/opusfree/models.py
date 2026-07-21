"""Shared data structures passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Word:
    """A single transcribed word with timing (seconds, relative to source)."""

    text: str
    start: float
    end: float


@dataclass
class Segment:
    """A transcript segment (roughly a sentence) with its words."""

    text: str
    start: float
    end: float
    words: List[Word] = field(default_factory=list)


@dataclass
class Transcript:
    """Full transcript of the source video."""

    segments: List[Segment] = field(default_factory=list)

    @property
    def words(self) -> List[Word]:
        out: List[Word] = []
        for seg in self.segments:
            out.extend(seg.words)
        return out

    @property
    def duration(self) -> float:
        return self.segments[-1].end if self.segments else 0.0


@dataclass
class Clip:
    """A candidate short clip cut from the source."""

    start: float
    end: float
    words: List[Word]
    score: int = 0            # 0-100 "virality" estimate
    title: str = ""
    reasons: List[str] = field(default_factory=list)
    breakdown: List[str] = field(default_factory=list)  # "factor: +pts" lines
    viral_score: float = 0.0  # 1-10 scale (spec)
    justification: str = ""   # why this clip should perform
    subscores: dict = field(default_factory=dict)  # consensus/vuln/utility/arc
    has_payoff: bool = True

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words).strip()
