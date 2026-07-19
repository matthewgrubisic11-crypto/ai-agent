"""Aspect-ratio helpers: map a 'W:H' string to output pixel dimensions.

Mirrors Opus's ReframeAnything targets: 9:16 (TikTok/Shorts), 1:1 (Instagram
feed), 16:9 (YouTube/LinkedIn), plus anything else you type.
"""

from __future__ import annotations

# Friendly platform labels for the manifest / UI.
PLATFORM = {
    "9:16": "TikTok / Reels / Shorts",
    "1:1": "Instagram feed",
    "4:5": "Instagram portrait",
    "16:9": "YouTube / LinkedIn",
}


def _even(n: float) -> int:
    """H.264 needs even dimensions."""
    return int(round(n / 2) * 2)


def parse_ratio(ratio: str, base: int = 1080) -> tuple[int, int, float]:
    """Return (out_w, out_h, ratio_value) for a 'W:H' string.

    The shorter side is fixed to ``base`` (1080) for consistent quality.
    """
    try:
        w_str, h_str = ratio.replace(" ", "").split(":")
        rw, rh = float(w_str), float(h_str)
        if rw <= 0 or rh <= 0:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"bad aspect ratio {ratio!r}; use e.g. 9:16") from exc

    value = rw / rh
    if value < 1:            # portrait -> width is the short side
        out_w, out_h = base, _even(base / value)
    elif value > 1:          # landscape -> height is the short side
        out_w, out_h = _even(base * value), base
    else:                    # square
        out_w = out_h = base
    return out_w, out_h, value


def ratio_tag(ratio: str) -> str:
    """Filename-safe tag, e.g. '9:16' -> '9x16'."""
    return ratio.replace(":", "x").replace(" ", "")
