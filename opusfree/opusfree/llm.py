"""Optional local-LLM reranking of candidate clips via Ollama.

Fully local and free: requires the Ollama app running (https://ollama.com)
with a model pulled, e.g. ``ollama pull llama3.1``. If anything goes wrong we
fall back silently to the heuristic scores so the pipeline never breaks.
"""

from __future__ import annotations

import json
from typing import List

from .models import Clip

_PROMPT = """You rate short-video clips cut from a longer talk/podcast.
For each clip, give a virality score 0-100 (how likely it grabs attention and
gets shared on TikTok/Reels/Shorts) and a punchy <=6 word title.
Return ONLY JSON: a list of objects {"i": <index>, "score": <int>, "title": <str>}.

Clips:
"""


def rerank_with_ollama(clips: List[Clip], model: str = "llama3.1") -> List[Clip]:
    try:
        import urllib.request

        listing = "\n".join(
            f'[{i}] ({c.duration:.0f}s) {c.text[:280]}' for i, c in enumerate(clips)
        )
        payload = {
            "model": model,
            "prompt": _PROMPT + listing,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
        data = json.loads(body.get("response", "[]"))
        if isinstance(data, dict):
            data = data.get("clips") or data.get("results") or []

        for item in data:
            i = int(item.get("i", -1))
            if 0 <= i < len(clips):
                clips[i].score = int(max(1, min(100, item.get("score", clips[i].score))))
                if item.get("title"):
                    clips[i].title = str(item["title"])[:80]
                clips[i].reasons = ["LLM-rated (ollama)"]
    except Exception as exc:  # pragma: no cover - best-effort enhancement
        print(f"  [llm] ollama rerank skipped ({exc}); using heuristic scores")
    return clips
