"""Tiny .env loader so an API key is a one-time paste, not a per-run export.

Reads KEY=VALUE lines from opusfree/.env (and the repo root) into the process
environment without overwriting anything already set. No dependency on
python-dotenv.
"""

from __future__ import annotations

import os


def load_env() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", ".env"),          # opusfree/.env
        os.path.join(here, "..", "..", ".env"),     # repo/.env
    ]
    for path in candidates:
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except OSError:
            pass
