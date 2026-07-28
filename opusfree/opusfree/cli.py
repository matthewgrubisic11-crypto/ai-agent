"""Command-line entry point for opusfree."""

from __future__ import annotations

import argparse
import sys

from .captions import STYLES
from .envfile import load_env
from .pipeline import process

load_env()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="opusfree",
        description="Turn one long video into scored, captioned, vertical clips "
                    "-- a free, fully-local Opus Clip alternative.",
    )
    parser.add_argument("video",
                        help="local video/audio file OR a link (YouTube etc.)")
    parser.add_argument("-o", "--out", default="clips", help="output directory")
    parser.add_argument("-n", "--count", type=int, default=10,
                        help="number of clips to produce (default 10)")
    parser.add_argument("--min", type=float, default=15.0, dest="min_dur",
                        help="min clip length in seconds (default 15)")
    parser.add_argument("--max", type=float, default=60.0, dest="max_dur",
                        help="max clip length in seconds (default 60)")
    parser.add_argument("--model", default="base",
                        help="whisper size: tiny|base|small|medium|large-v3")
    parser.add_argument("--language", default=None,
                        help="force a language code (e.g. en); default auto")
    parser.add_argument("--style", default="retention", choices=list(STYLES),
                        help="caption style")
    parser.add_argument("--llm", default=None, choices=["ollama"],
                        help="(legacy) force local ollama for the fallback path; "
                             "AI selection auto-detects Gemini/Groq/OpenAI/Ollama "
                             "from env keys regardless")
    parser.add_argument("--prompt", default=None,
                        help="ClipAnything: only clip moments matching this text")
    parser.add_argument("--ratios", default="9:16",
                        help="comma list of aspect ratios, e.g. 9:16,1:1,16:9")
    parser.add_argument("--no-meta", action="store_true",
                        help="skip AI titles/descriptions/hashtags")
    parser.add_argument("--no-zooms", action="store_true",
                        help="disable punch zooms on emphasis moments")
    parser.add_argument("--no-sfx", action="store_true",
                        help="disable the synthesized anticipation riser")
    parser.add_argument("--no-split", action="store_true",
                        help="disable automatic two-speaker split-screen")
    parser.add_argument("--no-tighten", action="store_true",
                        help="keep dead air / filler words (no surgical cut)")
    parser.add_argument("--no-enhance", action="store_true",
                        help="skip dialogue normalization/compression")
    parser.add_argument("--clean-audio", action="store_true",
                        help="noise removal (studio-clean dialogue)")
    parser.add_argument("--translate", action="store_true",
                        help="translate captions to English (any language)")
    parser.add_argument("--music", default=None,
                        help="path to a music file to duck under dialogue")
    parser.add_argument("--cta", default="Follow for more",
                        help="end-card call-to-action text ('' to disable)")
    args = parser.parse_args(argv)

    ratios = [r.strip() for r in args.ratios.split(",") if r.strip()]

    try:
        process(
            args.video, args.out, count=args.count, min_dur=args.min_dur,
            max_dur=args.max_dur, model_size=args.model, language=args.language,
            caption_style=args.style, use_llm=args.llm, prompt=args.prompt,
            ratios=ratios, gen_meta=not args.no_meta,
            zooms=not args.no_zooms, sfx=not args.no_sfx,
            split_screen=not args.no_split, tighten=not args.no_tighten,
            enhance_audio=not args.no_enhance, clean_audio=args.clean_audio,
            translate=args.translate, music_path=args.music,
            cta=args.cta or None,
        )
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
