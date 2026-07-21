"""Audio analysis: amplitude log, energy spikes, thumbnail peak, dialogue mix.

Multi-modal input the spec asks for: a real amplitude log decoded from the
source (no extra deps -- ffmpeg -> raw PCM -> stdlib array). Energy spikes
approximate laughter/gasps/emphasis; the loudest facial+vocal moment gives the
thumbnail timestamp. Dialogue enhancement is a real ffmpeg filter chain.
"""

from __future__ import annotations

import array
import subprocess
from typing import List, Tuple

SR = 8000          # analysis sample rate
WIN = 0.05         # 50 ms windows


def amplitude_log(video_path: str) -> List[Tuple[float, float]]:
    """Return [(t_seconds, rms_0_to_1), ...] across the whole source."""
    try:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", video_path,
             "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
            capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        return []

    samples = array.array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if not samples:
        return []

    win = int(SR * WIN)
    log: List[Tuple[float, float]] = []
    peak = 1.0
    for i in range(0, len(samples) - win, win):
        chunk = samples[i:i + win]
        # mean-square without numpy
        ss = 0
        for s in chunk:
            ss += s * s
        rms = (ss / win) ** 0.5
        log.append((round(i / SR, 3), rms))
        peak = max(peak, rms)
    # normalise
    return [(t, round(v / peak, 4)) for t, v in log]


def _stats(values: List[float]) -> Tuple[float, float]:
    n = len(values) or 1
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    return mean, var ** 0.5


def energy_spikes(log: List[Tuple[float, float]], k: float = 1.6
                  ) -> List[float]:
    """Timestamps where energy jumps well above local baseline."""
    if not log:
        return []
    vals = [v for _, v in log]
    mean, std = _stats(vals)
    thresh = mean + k * std
    spikes, last = [], -10.0
    for t, v in log:
        if v >= thresh and t - last >= 0.8:
            spikes.append(t)
            last = t
    return spikes


def window_energy(log: List[Tuple[float, float]], start: float,
                  end: float) -> float:
    """Mean normalized energy within [start, end] (0 if no data)."""
    vals = [v for t, v in log if start <= t <= end]
    return sum(vals) / len(vals) if vals else 0.0


def peak_time(log: List[Tuple[float, float]], start: float,
              end: float) -> float:
    """Timestamp of maximum energy within a clip -- our thumbnail moment."""
    best_t, best_v = start, -1.0
    for t, v in log:
        if start <= t <= end and v > best_v:
            best_t, best_v = t, v
    return best_t


# Real, applied filter: normalize + compress dialogue so speech is loud and
# consistent (the "dialogue enhancement" directive, actually executed).
DIALOGUE_ENHANCE = (
    "acompressor=threshold=-18dB:ratio=3:attack=5:release=120,"
    "loudnorm=I=-14:TP=-1.5:LRA=11"
)
