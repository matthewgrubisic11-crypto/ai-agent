# opusfree

A **free, fully-local** alternative to [Opus Clip](https://www.opus.pro/). Give it
one long video (podcast, webinar, talk, Zoom recording) and it produces a batch of
short clips — the best moments, scored, auto-reframed, with animated captions and
ready-to-paste social copy. No subscription, no API keys, nothing uploaded to anyone.
Runs on your own machine, with a **command line** *and* a **local web app**.

opusfree is an **AI video producer**: it doesn't just cut clips, it edits them —
surgical filler/dead-air removal, retention captions, simulated multicam, and a
full growth kit per clip.

## The AI brain (turn this ON — it's the difference)

The real tools (Opus, Submagic, OpenShorts) don't keyword-match — they run a
**language model over the whole transcript** to find genuinely viral moments.
opusfree does the same when it has an AI provider. Getting one is a one-time,
**free** paste:

1. Get a free key at **https://aistudio.google.com/apikey** (Google Gemini) —
   or Groq at https://console.groq.com/keys.
2. Copy `.env.example` to `.env` and paste it in:
   `GEMINI_API_KEY=your_key_here`
3. Done — it's detected automatically forever. The web UI shows **✓ AI brain ON**.

Without a key it still works using a built-in scorer (and can use local Ollama
if installed), but AI selection is dramatically better. This is the single
biggest lever on quality.

## What it does

| Capability | opusfree |
|---|---|
| Transcription (multi-language) | ✅ Whisper, word-level timestamps |
| **LLM highlight selection** | ✅ Whole-transcript virality framework via Gemini/Groq/OpenAI/Ollama |
| Multi-modal analysis | ✅ Transcript + audio-energy log (spikes → thumbnail, scoring) |
| Reframe fallback | ✅ **Blurred-fill background** when no face is confident (no blank walls) |
| Arc-based selection (no-key fallback) | ✅ Requires hook + payoff; scores consensus-breaking / vulnerability / utility |
| Virality score | ✅ 1–10 **and** 0–100, with a per-point breakdown you can inspect |
| **ClipAnything** (prompt) | ✅ Keyword/semantic matching (LLM-boosted with Ollama) |
| Surgical editing | ✅ Cuts filler ("um", "you know") + dead air >0.2s, restitches tight |
| Reframe 9:16 / 1:1 / 16:9 | ✅ Face-tracking crop + **auto split-screen** for two speakers |
| Kinetic captions | ✅ ≤3 words, centered, karaoke + **semantic color** (money→green, danger→red) + 🔥 |
| Simulated multicam | ✅ Punch-zoom pulses on emphasis, centered on the eyes |
| Jump-cut masking | ✅ Every cut gets a zoom/B-roll directive |
| Audio | ✅ Real dialogue normalize+compress; optional music ducking (`--music`) |
| Growth kit | ✅ 3 on-screen titles, SEO caption (hook / debate Q / 5 hashtags), thumbnail frame |
| Machine-readable output | ✅ `clips.json` with EDL + visual/audio directives per clip |
| Web app UI | ✅ `webrun.py` (drag-drop, toggles, previews, growth kit) |

### Honest boundaries (what's a *directive*, not a rendered asset)

Some spec features can't be produced locally for free, so opusfree emits the
**instruction** for them (in `clips.json`) rather than the finished asset:

- **Stock B-roll overlays** — it generates the B-roll *search queries* per abstract
  keyword, but doesn't fetch licensed footage (that needs a paid stock library).
- **Background music** — it picks a mood and writes the ducking directive; supply
  your own track with `--music song.mp3` and it *will* duck it under dialogue for real.
- **True emotion/diarization models** — micro-expression and speaker labels are
  approximated from audio energy + face tracking, not a trained classifier.
- **Virality model** — transparent, tunable logic, not Opus's proprietary weights.
- One-click posting to TikTok/YouTube needs paid platform partnerships, so posting
  stays manual (copy from the generated `.txt`).

Everything else — the cut, reframe, captions, zooms, audio, growth kit — is real.

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

## Host it on the web (permanent URL)

Want it always online at a URL instead of only on your machine? See
**[DEPLOY.md](DEPLOY.md)** — the easiest free option is Hugging Face Spaces
(permanent URL, wakes on visit). A `Dockerfile` is included so it deploys to
Spaces, Render, or Fly.io as-is.

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
