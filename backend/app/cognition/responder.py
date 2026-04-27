from __future__ import annotations

import re


def sanitize_for_tts(text: str) -> str:
    cleaned = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    cleaned = re.sub(r"[`*_]", "", cleaned)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", cleaned)
    return " ".join(cleaned.split())