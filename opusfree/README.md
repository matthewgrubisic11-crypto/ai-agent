# opusfree

A **free, fully-local** alternative to [Opus Clip](https://www.opus.pro/). Give it
one long video (podcast, webinar, talk, Zoom recording) and it produces a batch of
short clips — the best moments, scored, auto-reframed, with animated captions and
ready-to-paste social copy. No subscription, no API keys, nothing uploaded to anyone.
Runs on your own machine, with a **command line** *and* a **local web app**.

## Feature parity with Opus Clip

| Opus Clip feature | opusfree |
|---|---|
| Transcription (multi-language) | ✅ Whisper, local, word-level timestamps |
| Find the best moments | ✅ Sentence-aligned candidates + scorer |
| Virality Score (1–100) | ✅ Transparent heuristic (hooks, emotion, questions, length) |
| **ClipAnything** (prompt: "clip every moment about X") | ✅ Keyword/semantic matching (LLM-boosted with `--llm`) |
| ReframeAnything → 9:16 / 1:1 / 16:9 | ✅ OpenCV speaker-tracking crop, any ratio |
| Active-speaker centered reframe | ✅ Largest-face tracking |
| Animated captions | ✅ ASS karaoke, 3 styles |
| AI titles / descriptions / hashtags | ✅ Local LLM (Ollama) or keyword fallback |
| Export MP4 | ✅ ffmpeg, 1080p |
| Web app UI | ✅ `webrun.py` (drag-drop, progress, previews) |

**What can't be identical (and why):** Opus's ClipAnything and Virality models are
proprietary neural nets trained on private data — this uses transparent, *tunable*
logic that does the same job, not their exact weights. One-click posting to
TikTok/YouTube needs their paid platform partnerships, so that stays manual here
(opusfree writes the caption + hashtags into a `.txt` next to each clip for you to
paste). And it runs at your machine's speed, not their cloud GPUs. Everything that
makes the actual clips is here.

## Install

```bash
# 1. ffmpeg binaries
brew install ffmpeg                # macOS
sudo apt install ffmpeg           # Ubuntu/Debian
# Windows: https://ffmpeg.org/download.html  (add to PATH)

# 2. Python deps (Python 3.10+)
cd opusfree
pip install -r requirements.txt

# 3. (optional) smarter picks + AI copy, still local & free
#    install Ollama from https://ollama.com, then:  ollama pull llama3.1
```

## Use — web app (easiest)

```bash
python webrun.py          # then open http://localhost:8500
```
Drag in a video, set options (ClipAnything prompt, clip count, ratios, caption
style, Ollama on/off), hit **Generate**, watch the progress bar, then preview and
download each clip and its copy.

## Use — command line

```bash
# 10 clips from a local file into ./clips/
python run.py talk.mp4

# ClipAnything: only the moments about a topic
python run.py talk.mp4 --prompt "advice for first-time founders"

# multiple aspect ratios at once
python run.py talk.mp4 --ratios 9:16,1:1,16:9

# tune length + caption style + more accurate transcription
python run.py talk.mp4 -n 6 --min 20 --max 45 --style hormozi --model small

# smartest picks + AI copy via local LLM
python run.py talk.mp4 --llm ollama
```

Each clip is written as `01_score87_your-hook_9x16.mp4`, with a matching `.txt`
of title/description/hashtags, plus a `clips.json` manifest of everything.

### Options

| Flag | Meaning | Default |
|------|---------|---------|
| `-o, --out` | output directory | `clips` |
| `-n, --count` | how many clips | `10` |
| `--min` / `--max` | clip length bounds (s) | `15` / `60` |
| `--prompt` | ClipAnything: only clip matching moments | off |
| `--ratios` | comma list, e.g. `9:16,1:1,16:9` | `9:16` |
| `--model` | whisper size `tiny…large-v3` | `base` |
| `--language` | force a language code | auto |
| `--style` | `bold-yellow`, `clean-white`, `hormozi` | `bold-yellow` |
| `--llm` | `ollama` — smarter picks + AI copy | off |
| `--no-meta` | skip AI titles/hashtags | off |

## How it fits together

```
run.py / webrun.py ─▶ cli.py / webapp.py ─▶ pipeline.py
                                                │
   transcribe.py ── words+times ────────────────┤
   select.py     ── scored clips / ClipAnything ┤
   meta.py       ── titles + hashtags ──────────┤
   aspect.py     ── 9:16 / 1:1 / 16:9 sizes ────┤
   reframe.py    ── speaker-tracking crop ──────┤
   captions.py   ── ASS karaoke subs ───────────┤
   render.py     ── ffmpeg MP4 ─────────────────┘
```

## Tuning the "virality model"

Open `opusfree/select.py`. `HOOK_WORDS` / `EMOTION_WORDS` and the weights in
`_score()` are plain, editable code — bump what matters for your niche. That's the
whole scoring model, fully in your hands (something Opus won't let you touch).

## Test

```bash
python examples/selftest.py     # exercises selection, ClipAnything, captions,
                                # aspect ratios, metadata, upload parsing
```
