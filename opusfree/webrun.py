#!/usr/bin/env python3
"""Launch the opusfree web UI: python webrun.py  ->  http://localhost:8500"""

import argparse

from opusfree.webapp import run

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="opusfree local web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8500)
    a = p.parse_args()
    run(a.host, a.port)
