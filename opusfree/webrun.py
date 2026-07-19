#!/usr/bin/env python3
"""Launch the opusfree web UI.

Local:  python webrun.py            -> http://localhost:8500 (localhost only)
Hosted: HOST=0.0.0.0 PORT=7860 ...  -> binds all interfaces (Docker/Spaces)

Env vars HOST and PORT override the defaults, so the same image works on
Hugging Face Spaces (PORT=7860), Render, Fly.io, etc. without code changes.
"""

import argparse
import os

from opusfree.webapp import run

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="opusfree local web UI")
    p.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8500")))
    a = p.parse_args()
    run(a.host, a.port)
