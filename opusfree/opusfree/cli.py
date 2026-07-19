"""Command-line entry point for opusfree."""

from __future__ import annotations

import argparse
import sys

from .captions import STYLES
from .pipeline import process


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="opusfree",
        description="Turn one long video into scored, captioned, vertical clips "
                    "-- a free, fully-local Opus Clip alternative.",
    )
    parser.add_argument("video", help="path to a local video/audio file")
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
    parser.add_argument("--style", default="bold-yellow", choices=list(STYLES),
                        help="caption style")
    parser.add_argument("--llm", default=None, choices=["ollama"],
                        help="use a local LLM (ollama) for smarter picks + copy")
    parser.add_argument("--prompt", default=None,
                        help="ClipAnything: only clip moments matching this text")
    parser.add_argument("--ratios", default="9:16",
                        help="comma list of aspect ratios, e.g. 9:16,1:1,16:9")
    parser.add_argument("--no-meta", action="store_true",
                        help="skip AI titles/descriptions/hashtags")
    args = parser.parse_args(argv)

    ratios = [r.strip() for r in args.ratios.split(",") if r.strip()]

    try:
        process(
            args.video, args.out, count=args.count, min_dur=args.min_dur,
            max_dur=args.max_dur, model_size=args.model, language=args.language,
            caption_style=args.style, use_llm=args.llm, prompt=args.prompt,
            ratios=ratios, gen_meta=not args.no_meta,
        )
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
