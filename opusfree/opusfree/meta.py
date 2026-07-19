"""Generate a title, description, and hashtags for each clip.

Matches Opus's Social Scheduler text output. Uses a local Ollama LLM when
available (--llm ollama) for natural copy; otherwise falls back to a keyword
heuristic so you always get usable metadata with zero setup.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import List

from .models import Clip

_STOP = {
    "the", "a", "an", "and", "or", "but", "if", "to", "of", "in", "on", "for",
    "with", "is", "are", "was", "were", "be", "been", "it", "its", "this",
    "that", "these", "those", "i", "you", "he", "she", "they", "we", "me",
    "my", "your", "our", "so", "just", "like", "really", "very", "about",
    "here", "there", "what", "when", "how", "why", "at", "as", "by", "from",
    "not", "no", "do", "does", "did", "have", "has", "had", "will", "would",
    "can", "could", "should", "get", "got", "going", "gonna", "yeah", "okay",
}


def _keywords(text: str, k: int = 6) -> List[str]:
    tokens = re.findall(r"[a-zA-Z']+", text.lower())
    counts = Counter(t for t in tokens if t not in _STOP and len(t) > 2)
    return [w for w, _ in counts.most_common(k)]


def _heuristic(clip: Clip, platform: str) -> dict:
    words = clip.text.split()
    title = " ".join(words[:9]).strip().rstrip(".,;:")
    title = (title[:1].upper() + title[1:]) if title else "Untitled clip"
    kws = _keywords(clip.text)
    hashtags = ["#" + re.sub(r"[^a-z0-9]", "", w) for w in kws]
    hashtags += ["#shorts", "#viral", "#fyp"]
    # de-dupe preserving order
    seen, tags = set(), []
    for h in hashtags:
        if h not in seen and len(h) > 1:
            seen.add(h)
            tags.append(h)
    desc = clip.text[:180].strip()
    if len(clip.text) > 180:
        desc = desc.rsplit(" ", 1)[0] + "..."
    return {"title": title, "description": desc, "hashtags": tags[:8]}


def _ollama(clip: Clip, platform: str, model: str = "llama3.1") -> dict | None:
    try:
        import urllib.request

        prompt = (
            f"Write social copy for a short video clip for {platform}.\n"
            f"Transcript: \"{clip.text[:600]}\"\n"
            "Return ONLY JSON: {\"title\": <catchy <=70 chars>, "
            "\"description\": <1-2 sentences>, "
            "\"hashtags\": [<6-8 relevant hashtags with #>]}"
        )
        payload = {"model": model, "prompt": prompt, "stream": False,
                   "format": "json", "options": {"temperature": 0.6}}
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
        data = json.loads(body.get("response", "{}"))
        if data.get("title"):
            tags = data.get("hashtags") or []
            tags = ["#" + t.lstrip("#") for t in tags if str(t).strip()]
            return {
                "title": str(data["title"])[:80],
                "description": str(data.get("description", ""))[:300],
                "hashtags": tags[:8],
            }
    except Exception:
        return None
    return None


def generate_metadata(clip: Clip, platform: str = "TikTok",
                      use_llm: str | None = None) -> dict:
    """Return {'title', 'description', 'hashtags'} for a clip."""
    if use_llm == "ollama":
        result = _ollama(clip, platform)
        if result:
            return result
    return _heuristic(clip, platform)
