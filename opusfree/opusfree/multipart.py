"""Minimal multipart/form-data parser (stdlib only).

Replaces the removed-in-3.13 ``cgi`` module for our one upload form. Parses a
raw POST body into text fields and a single uploaded file. Not a general-purpose
parser -- just enough for opusfree's web UI.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple


def parse(body: bytes, content_type: str
          ) -> Tuple[Dict[str, str], Optional[Tuple[str, bytes]]]:
    """Return (fields, file) where file is (filename, bytes) or None."""
    m = re.search(r"boundary=([^;]+)", content_type)
    if not m:
        return {}, None
    boundary = m.group(1).strip().strip('"').encode()
    delim = b"--" + boundary

    fields: Dict[str, str] = {}
    upload: Optional[Tuple[str, bytes]] = None

    for part in body.split(delim):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        head, _, data = part.partition(b"\r\n\r\n")
        if not _:
            continue
        headers = head.decode("utf-8", "replace")
        name_m = re.search(r'name="([^"]*)"', headers)
        if not name_m:
            continue
        name = name_m.group(1)
        file_m = re.search(r'filename="([^"]*)"', headers)
        if file_m and file_m.group(1):
            upload = (file_m.group(1), data)
        else:
            fields[name] = data.decode("utf-8", "replace")

    return fields, upload
