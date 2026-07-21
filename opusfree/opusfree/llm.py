"""Optional local-LLM reranking of candidate clips via Ollama.

Fully local and free: requires the Ollama app running (https://ollama.com)
with a model pulled, e.g. ``ollama pull llama3.1``. If anything goes wrong we
fall back silently to the heuristic scores so the pipeline never breaks.
"""

from __future__ import annotations

import json
from typing import List

from .models import Clip


def ollama_available(timeout: float = 1.0) -> bool:
    """True if a local Ollama server is running with at least one model."""
    try:
        import urllib.request

        with urllib.request.urlopen("http://localhost:11434/api/tags",
                                    timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        return bool(data.get("models"))
    except Exception:
        return False

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


_RELEVANCE_PROMPT = """You judge how well each clip matches a user's request.
Request: "{prompt}"
For each clip give a relevance 0.0-1.0 (1.0 = perfectly on-topic).
Return ONLY JSON: a list of {{"i": <index>, "relevance": <float>}}.

Clips:
"""


def score_relevance_with_ollama(clips: List[Clip], prompt: str,
                                model: str = "llama3.1") -> List[Clip]:
    """Attach a ``_relevance`` (0-1) to each clip for ClipAnything-style search."""
    for c in clips:
        c._relevance = 0.0
    try:
        import urllib.request

        listing = "\n".join(
            f'[{i}] {c.text[:280]}' for i, c in enumerate(clips)
        )
        payload = {
            "model": model,
            "prompt": _RELEVANCE_PROMPT.format(prompt=prompt) + listing,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode())
        data = json.loads(body.get("response", "[]"))
        if isinstance(data, dict):
            data = data.get("clips") or data.get("results") or []
        for item in data:
            i = int(item.get("i", -1))
            if 0 <= i < len(clips):
                clips[i]._relevance = float(max(0.0, min(1.0, item.get("relevance", 0.0))))
    except Exception as exc:  # pragma: no cover
        print(f"  [llm] ollama relevance skipped ({exc}); using keyword matching")
    return clips


_GROWTH_PROMPT = """You are a viral short-form video strategist.
For this clip transcript, return ONLY JSON:
{{"on_screen_titles": [<3 punchy overlay titles, <=8 words each>],
  "post_caption": "<hook line>\\n\\n<a controversial or open-ended question>\\n\\n<5 hashtags: 3 niche + 2 broad>"}}
Transcript: "{text}"
"""


def growth_kit_with_ollama(clip, model: str = "llama3.1") -> dict | None:
    try:
        import urllib.request

        payload = {"model": model,
                   "prompt": _GROWTH_PROMPT.format(text=clip.text[:700]),
                   "stream": False, "format": "json",
                   "options": {"temperature": 0.7}}
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
        data = json.loads(body.get("response", "{}"))
        titles = data.get("on_screen_titles") or []
        if titles and data.get("post_caption"):
            return {"on_screen_titles": [str(t)[:70] for t in titles[:3]],
                    "post_caption": str(data["post_caption"])[:600]}
    except Exception:
        return None
    return None
