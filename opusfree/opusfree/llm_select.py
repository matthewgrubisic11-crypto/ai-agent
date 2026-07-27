"""LLM-first highlight selection -- the way Opus/Submagic/OpenShorts do it.

Feed the whole transcript (with timestamps) to a language model under a
virality framework and get back ranked, self-contained segments with a score,
category, hook, and reason. Timestamps are snapped back to real word
boundaries so cuts land cleanly.

Providers (auto-detected from env, best free option first):
  GEMINI_API_KEY  -> Google Gemini Flash   (free tier, strong)   [recommended]
  GROQ_API_KEY    -> Groq Llama-3.3-70B     (free tier, fast)
  OPENAI_API_KEY  -> OpenAI gpt-4o-mini     (paid)
  (Ollama running) -> local llama3.1        (free, needs a decent machine)

If none is available, the caller falls back to the heuristic scorer.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import List, Optional

from .models import Clip, Transcript, Word

VIRALITY_CRITERIA = [
    "HOOK: a shocking, contrarian, or high-stakes opening line",
    "EMOTIONAL PEAK: raw vulnerability, passion, anger, awe, or laughter",
    "OPINION BOMB: a strong, divisive, or contrarian take",
    "REVELATION: a surprising fact, secret, or 'nobody tells you' moment",
    "CONFLICT: tension, disagreement, or a hard truth",
    "QUOTABLE: a punchy, screenshot-able one-liner",
    "STORY PEAK: the turning point or climax of a personal story",
    "PRACTICAL VALUE: immediately actionable, specific advice",
]

SYSTEM_PROMPT = """You are an elite short-form video producer who has studied \
millions of viral TikToks, Reels, and Shorts. You find the moments in a \
long interview/podcast that will actually stop the scroll.

You will get a timestamped transcript. Return the BEST self-contained clips.

Every clip MUST:
- be {min_dur}-{max_dur} seconds long
- start EXACTLY on the first word of a complete thought (NEVER on a greeting, \
"so", "and", "but", "well", "um", or mid-sentence)
- contain a clear HOOK in the first 3 seconds
- deliver a clear PAYOFF/punchline/resolution by the end (never cut off a thought)
- stay on ONE topic (do not bleed into unrelated conversation)

Rank by these viral signals:
{criteria}

Score each clip 0-100 (100 = certain viral). Be honest and use the full range; \
most clips are 40-70, reserve 85+ for genuinely exceptional moments.

Content type: {content_type}. Tune your picks to that format.

Return ONLY JSON:
{{"clips":[{{"start": <sec>, "end": <sec>, "score": <int 0-100>, \
"category": "<HOOK|EMOTIONAL PEAK|OPINION BOMB|REVELATION|CONFLICT|QUOTABLE|\
STORY PEAK|PRACTICAL VALUE>", "title": "<punchy <=8 word on-screen title>", \
"hook": "<the exact opening line>", "reason": "<1 sentence: why it will perform>"}}]}}
"""


def _provider() -> Optional[tuple[str, str, str]]:
    """Return (provider, model, key) or None. Env overrides everything."""
    forced = os.environ.get("OPUSFREE_LLM_PROVIDER", "").lower()
    model_env = os.environ.get("OPUSFREE_LLM_MODEL", "")

    def pick(p, default_model, key):
        return (p, model_env or default_model, key)

    if forced == "gemini" or (not forced and os.environ.get("GEMINI_API_KEY")):
        key = os.environ.get("GEMINI_API_KEY", "")
        if key:
            return pick("gemini", "gemini-2.5-flash", key)
    if forced == "groq" or (not forced and os.environ.get("GROQ_API_KEY")):
        key = os.environ.get("GROQ_API_KEY", "")
        if key:
            return pick("groq", "llama-3.3-70b-versatile", key)
    if forced == "openai" or (not forced and os.environ.get("OPENAI_API_KEY")):
        key = os.environ.get("OPENAI_API_KEY", "")
        if key:
            return pick("openai", "gpt-4o-mini", key)
    if forced == "ollama" or _ollama_up():
        return pick("ollama", "llama3.1", "")
    return None


def _ollama_up() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags",
                                    timeout=1.0) as r:
            return bool(json.loads(r.read().decode()).get("models"))
    except Exception:
        return False


def available() -> Optional[str]:
    p = _provider()
    return p[0] if p else None


def _post(url: str, payload: dict, headers: dict, timeout: float = 180) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _complete(system: str, user: str) -> str:
    """Send a chat completion, return raw text (expected to be JSON)."""
    prov = _provider()
    if not prov:
        return "{}"
    provider, model, key = prov

    if provider == "gemini":
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={key}")
        body = {"contents": [{"parts": [{"text": system + "\n\n" + user}]}],
                "generationConfig": {"temperature": 0.4,
                                     "responseMimeType": "application/json"}}
        data = _post(url, body, {})
        return data["candidates"][0]["content"]["parts"][0]["text"]

    if provider in ("groq", "openai"):
        base = ("https://api.groq.com/openai/v1" if provider == "groq"
                else "https://api.openai.com/v1")
        body = {"model": model, "temperature": 0.4,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        data = _post(f"{base}/chat/completions", body,
                     {"Authorization": f"Bearer {key}"})
        return data["choices"][0]["message"]["content"]

    # ollama
    body = {"model": model, "prompt": system + "\n\n" + user,
            "stream": False, "format": "json",
            "options": {"temperature": 0.4}}
    data = _post("http://localhost:11434/api/generate", body, {})
    return data.get("response", "{}")


def _serialize(words: List[Word], max_words: int = 4500) -> List[List[Word]]:
    """Chunk words for the LLM (long videos exceed context)."""
    if len(words) <= max_words:
        return [words]
    chunks, i = [], 0
    overlap = 200
    while i < len(words):
        chunks.append(words[i:i + max_words])
        i += max_words - overlap
    return chunks


def _transcript_text(words: List[Word]) -> str:
    """Compact timestamped transcript: one line per ~sentence with a start ts."""
    lines, cur, cur_start = [], [], None
    for w in words:
        if cur_start is None:
            cur_start = w.start
        cur.append(w.text)
        if w.text[-1:] in ".!?" or len(cur) >= 18:
            lines.append(f"[{cur_start:.1f}] {' '.join(cur)}")
            cur, cur_start = [], None
    if cur:
        lines.append(f"[{cur_start:.1f}] {' '.join(cur)}")
    return "\n".join(lines)


def _snap(words: List[Word], start: float, end: float,
          min_dur: float, max_dur: float) -> Optional[List[Word]]:
    """Match LLM start/end (seconds) to real word boundaries."""
    # nearest word whose start >= requested start (a clean sentence-ish start)
    si = min(range(len(words)), key=lambda i: abs(words[i].start - start))
    # walk back to a sentence boundary if we're mid-sentence
    while si > 0 and words[si - 1].text[-1:] not in ".!?" and \
            words[si].start - start > -1.5:
        if start - words[si - 1].start > 1.2:
            break
        si -= 1
    ei = min(range(len(words)), key=lambda i: abs(words[i].end - end))
    if ei <= si:
        return None
    seg = words[si:ei + 1]
    dur = seg[-1].end - seg[0].start
    if dur < min_dur * 0.6 or dur > max_dur * 1.4:
        return None
    return seg


def detect_content_type(words: List[Word]) -> str:
    text = " ".join(w.text for w in words[:400]).lower()
    if text.count("?") > 8:
        return "interview / Q&A"
    if any(k in text for k in ("welcome back", "episode", "podcast", "my guest")):
        return "podcast"
    if any(k in text for k in ("step", "how to", "tutorial", "first you")):
        return "tutorial"
    return "interview / podcast"


def select_highlights(transcript: Transcript, count: int = 10,
                      min_dur: float = 20.0, max_dur: float = 60.0,
                      prompt: str | None = None) -> Optional[List[Clip]]:
    """LLM highlight ranking. Returns clips, or None if no LLM is available."""
    if not _provider():
        return None
    words = transcript.words
    if not words:
        return []

    content_type = detect_content_type(words)
    system = SYSTEM_PROMPT.format(
        min_dur=int(min_dur), max_dur=int(max_dur),
        criteria="\n".join(f"- {c}" for c in VIRALITY_CRITERIA),
        content_type=content_type)

    all_clips: List[Clip] = []
    for chunk in _serialize(words):
        user = "TRANSCRIPT:\n" + _transcript_text(chunk)
        if prompt:
            user += (f"\n\nEXTRA INSTRUCTION FROM USER (prioritize this): "
                     f"{prompt}")
        try:
            raw = _complete(system, user)
            data = json.loads(raw)
        except Exception as exc:  # pragma: no cover - network/parse
            print(f"  [llm] provider call failed ({exc}); ", end="")
            return None
        for item in (data.get("clips") or []):
            try:
                seg = _snap(chunk, float(item["start"]), float(item["end"]),
                            min_dur, max_dur)
            except (KeyError, ValueError, TypeError):
                continue
            if not seg:
                continue
            c = Clip(start=seg[0].start, end=seg[-1].end, words=list(seg))
            c.score = int(max(1, min(100, item.get("score", 60))))
            c.viral_score = round(c.score / 10.0, 1)
            c.title = str(item.get("title") or item.get("hook") or "")[:80]
            c.justification = str(item.get("reason", ""))[:200]
            cat = str(item.get("category", "")).strip()
            c.reasons = [cat.lower()] if cat else []
            c.subscores = {"llm_category": cat}
            c.has_payoff = True
            all_clips.append(c)

    # dedup overlaps, keep best
    all_clips.sort(key=lambda c: c.score, reverse=True)
    kept: List[Clip] = []
    for c in all_clips:
        if all(not (c.start < k.end and c.end > k.start) for k in kept):
            kept.append(c)
    return kept[:count]
