from __future__ import annotations

import re
from typing import Literal

from backend.app.personality.policy import PersonalityPolicy


Modality = Literal["text", "voice"]

_GENERIC_ACK_RE = re.compile(r"^(?:sure|okay|ok|certainly|absolutely)[,.!\s]+", re.IGNORECASE)


def apply_personality_style_guard(text: str, policy: PersonalityPolicy, *, modality: Modality) -> str:
    cleaned = " ".join(text.split())
    if _prefers_trimmed_acknowledgment(policy, modality):
        cleaned = _GENERIC_ACK_RE.sub("", cleaned).lstrip()
    return cleaned


def _prefers_trimmed_acknowledgment(policy: PersonalityPolicy, modality: Modality) -> bool:
    style_text = "\n".join(policy.style_rules).lower()
    if "acknowledgment style: none" in style_text:
        return True
    if modality == "voice" and "acknowledgment style: minimal" in style_text:
        return True
    return False
