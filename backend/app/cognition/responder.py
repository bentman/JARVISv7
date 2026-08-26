from __future__ import annotations

import re

_TURN_MARKER_RE = re.compile(r"(?im)^\s*(?:User|Assistant)\s*:")


def bound_single_turn_response(text: str) -> str:
    cleaned = text.strip()
    if cleaned.lower().startswith("assistant:"):
        cleaned = cleaned.split(":", 1)[1].lstrip()
    marker = _TURN_MARKER_RE.search(cleaned)
    if marker is not None:
        cleaned = cleaned[: marker.start()].rstrip()
    return cleaned


def sanitize_for_tts(text: str) -> str:
    cleaned = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    cleaned = re.sub(r"[`*_]", "", cleaned)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", cleaned)
    return " ".join(cleaned.split())
