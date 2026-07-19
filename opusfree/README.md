# opusfree

A **free, fully-local** alternative to [Opus Clip](https://www.opus.pro/). Give it
one long video (podcast, webinar, talk, Zoom recording) and it produces a batch of
short **vertical clips** — the best moments, scored, auto-reframed to 9:16, with
animated word-by-word captions burned in. No subscription, no API keys, no upload.
Everything runs on your own machine.

## What it does (and how it maps to Opus Clip)

| Opus Clip feature            | How opusfree does it                              |
|------------------------------|---------------------------------------------------|
| Transcription                | OpenAI **Whisper**, locally, with word timestamps |
| Find the best moments        | Sentence-aligned candidates + a transparent scorer|
| Virality score (1–100)       | Heuristic on hooks, emotion, questions, length, completeness (optionally re-ranked by a local LLM) |
| Auto-reframe to 9:16         | OpenCV face tracking → speaker-centred crop       |
| Animated captions            | ASS karaoke subtitles burned in via ffmpeg        |
| Export MP4                   | ffmpeg (H.264 + AAC, 1080×1920)                   |

**Honest caveat:** Opus Clip's virality model is proprietary and trained on private
data — this can't reproduce it exactly. The scorer here is a good, *tunable*
heuristic (see `opusfree/select.py`), not a black box. Everything else is on par.

## Install

You need Python 3.10+ and the **ffmpeg** binaries, then the Python deps:

```bash
# 1. ffmpeg (choose your OS)
brew install ffmpeg                 # macOS
sudo apt install ffmpeg            # Ubuntu/Debian
# Windows: https://ffmpeg.org/download.html  (add to PATH)

# 2. Python deps
cd opusfree
pip install -r requirements.txt
```

The first run downloads the Whisper model (a few hundred MB for `base`) once.

## Use

```bash
# simplest: 10 clips from a local file into ./clips/
python run.py /path/to/talk.mp4

# tune it
python run.py talk.mp4 -o out -n 6 --min 20 --max 45 --style hormozi

# more accurate transcription (slower; wants a GPU for large)
python run.py talk.mp4 --model small

# smarter clip picks with a local LLM (needs Ollama running)
ollama pull llama3.1
python run.py talk.mp4 --llm ollama
```

Output: one MP4 per clip named `01_score87_your-hook-here.mp4`, plus a
`clips.json` manifest with every clip's score, timing, title, and reasons.

### Options

| Flag | Meaning | Default |
|------|---------|---------|
| `-o, --out` | output directory | `clips` |
| `-n, --count` | how many clips | `10` |
| `--min` / `--max` | clip length bounds (s) | `15` / `60` |
| `--model` | whisper size: `tiny…large-v3` | `base` |
| `--language` | force a language code | auto |
| `--style` | `bold-yellow`, `clean-white`, `hormozi` | `bold-yellow` |
| `--llm` | `ollama` to re-rank picks | off |
| `--size` | output `WxH` | `1080x1920` |

## How it fits together

```
run.py ─▶ opusfree/cli.py ─▶ pipeline.py
                                 │
   transcribe.py  ── words+times ┤
   select.py      ── scored clips┤
   reframe.py     ── 9:16 crop   ┤
   captions.py    ── ASS subs    ┤
   render.py      ── ffmpeg MP4  ┘
```

## Speed

- `tiny`/`base` Whisper run fine on a laptop CPU. `small`+ are much better but want a GPU.
- Rendering is CPU H.264 (`libx264 veryfast`). A 60-min source → ~10 clips typically
  takes a few minutes on a modern laptop.

## Tuning the scorer

Open `opusfree/select.py`. `HOOK_WORDS`/`EMOTION_WORDS` and the weights in `_score()`
are plain and editable — bump what matters for your niche. That's the whole "virality
model," fully in your hands.
