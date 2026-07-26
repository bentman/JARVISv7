from __future__ import annotations

import json

from backend.app.artifacts.turn_artifact import TurnArtifact
from backend.app.cognition.memory_extraction import (
    EXTRACTION_MAX_TOKENS,
    MAX_EXTRACTION_TURNS,
    MAX_TURN_FIELD_CHARS,
    MemoryCandidateExtractor,
)
from backend.app.memory.curation_contract import (
    MAX_CANDIDATES,
    MAX_MODEL_OUTPUT_CHARS,
    MAX_MODEL_EVIDENCE_REFS,
    MAX_MODEL_EXCERPT_CHARS,
    MAX_MODEL_TEXT_CHARS,
    MAX_MODEL_TURN_ID_CHARS,
)
from backend.app.cognition.prompt_envelope import PromptEnvelope
from backend.app.runtimes.llm.base import LLMBase


class FakeEnvelopeLLM(LLMBase):
    def __init__(self, output: str) -> None:
        self.output = output
        self.envelope: PromptEnvelope | None = None

    def generate(self, prompt: str, **kwargs: object) -> str:
        raise AssertionError("extractor must use generate_envelope")

    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        self.envelope = envelope
        return self.output

    def is_available(self) -> bool:
        return True

    def runtime_name(self) -> str:
        return "fake"


def test_extractor_uses_trusted_contract_untrusted_bounded_evidence() -> None:
    llm = FakeEnvelopeLLM('{"candidates":[]}')
    turns = tuple(
        TurnArtifact(
            turn_id=f"turn-{index}",
            session_id="session-1",
            input_modality="text",
            final_state="IDLE",
            transcript="x" * 600,
            response_text="response",
        )
        for index in range(14)
    )

    result = MemoryCandidateExtractor(llm).extract(
        session_id="session-1",
        turns=turns,
    )

    assert result.proposals == ()
    assert len(result.persisted_turns) == MAX_EXTRACTION_TURNS
    assert result.persisted_turns[0].turn_id == "turn-12"
    assert len(result.persisted_turns[0].transcript or "") == MAX_TURN_FIELD_CHARS
    assert llm.envelope is not None
    assert llm.envelope.generation == {"max_tokens": EXTRACTION_MAX_TOKENS}
    assert [(segment.authority, segment.trusted) for segment in llm.envelope.segments] == [
        ("application", True),
        ("output", True),
        ("session", False),
        ("user", False),
    ]
    session_payload = json.loads(llm.envelope.segments[2].text)
    assert session_payload["turns"][0]["turn_id"] == "turn-12"
    contract = llm.envelope.segments[1].text
    assert "text (1..96 chars), evidence_refs" in contract
    assert "kind" not in contract
    assert "claim_key" not in contract
    assert "relation" not in contract
    assert "confidence" not in contract
    assert "importance" not in contract
    assert "source_field (transcript)" in contract
    assert "response_text" not in contract


def test_extraction_budget_covers_maximum_valid_bounded_output() -> None:
    candidate = {
        "text": "x" * MAX_MODEL_TEXT_CHARS,
        "evidence_refs": [
            {
                "source_turn_id": "t" * MAX_MODEL_TURN_ID_CHARS,
                "source_field": "transcript",
                "excerpt": "e" * MAX_MODEL_EXCERPT_CHARS,
            }
        ]
        * MAX_MODEL_EVIDENCE_REFS,
    }
    raw_output = json.dumps(
        {"candidates": [candidate] * MAX_CANDIDATES},
        separators=(",", ":"),
    )
    raw_output += " " * (MAX_MODEL_OUTPUT_CHARS - len(raw_output))
    assert len(raw_output) == MAX_MODEL_OUTPUT_CHARS

    llm = FakeEnvelopeLLM(raw_output)
    result = MemoryCandidateExtractor(llm).extract(
        session_id="session-1",
        turns=(),
    )

    assert len(result.proposals) == MAX_CANDIDATES
    assert EXTRACTION_MAX_TOKENS >= len(raw_output)
    assert llm.envelope is not None
    assert llm.envelope.generation == {"max_tokens": EXTRACTION_MAX_TOKENS}
