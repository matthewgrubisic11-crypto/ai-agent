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
                        help="use a local LLM (ollama) to rerank clips")
    parser.add_argument("--size", default="1080x1920",
                        help="output WxH (default 1080x1920 for 9:16)")
    args = parser.parse_args(argv)

    try:
        out_w, out_h = (int(x) for x in args.size.lower().split("x"))
    except ValueError:
        parser.error("--size must look like 1080x1920")

    try:
        process(
            args.video, args.out, count=args.count, min_dur=args.min_dur,
            max_dur=args.max_dur, model_size=args.model, language=args.language,
            caption_style=args.style, use_llm=args.llm, out_w=out_w, out_h=out_h,
        )
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
