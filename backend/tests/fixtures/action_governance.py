from __future__ import annotations

from typing import Any
from uuid import uuid4

from backend.app.actions.boundaries import ActionOperation
from backend.app.actions.catalog import (
    SEARCH_PRIVATE_WEB,
    SEARCH_PUBLIC_WEB,
    CapabilityObservation,
)
from backend.app.actions.contracts import ModelActionProposal
from backend.app.services.capability_service import (
    CapabilityHandler,
    CapabilityService,
)
from backend.app.services.search_service import SearchService
from backend.tests.fixtures.search_providers import MockSearchProvider


def _build_search_handler(search_service: SearchService) -> CapabilityHandler:
    """Build a capability handler that delegates to SearchService."""

    def handler(arguments: dict[str, Any], operation: ActionOperation) -> dict[str, Any]:
        session_id = operation.session_id
        turn_id = operation.turn_id
        with search_service.operation(session_id, turn_id) as search_op:
            evidence = search_service.retrieve(
                search_op,
                mode=arguments["mode"],
                topic=arguments["topic"],
                queries=arguments["queries"],
            )
        return search_op.snapshot()

    return handler


def make_capability_service_with_mock_search(
    providers: list[MockSearchProvider],
) -> CapabilityService:
    """Create a :class:`CapabilityService` with mock search providers wired in.

    The returned service has search capabilities marked as available.
    All other capabilities (memory, provider store, etc.) are unavailable.
    """
    search_service = SearchService(list(providers))
    handler = _build_search_handler(search_service)

    def observe() -> CapabilityObservation:
        return CapabilityObservation(
            search_providers=tuple(
                (provider.runtime_name(), True) for provider in providers
            ),
        )

    handlers: dict[str, CapabilityHandler] = {
        SEARCH_PUBLIC_WEB: handler,
        SEARCH_PRIVATE_WEB: handler,
    }
    return CapabilityService(observe=observe, handlers=handlers)


def make_search_proposal(
    query: str,
    private: bool = False,
) -> ModelActionProposal:
    """Build a valid search proposal matching the catalog's expected shape."""
    capability_id = SEARCH_PRIVATE_WEB if private else SEARCH_PUBLIC_WEB
    return ModelActionProposal(
        proposal_id=uuid4().hex,
        capability_id=capability_id,
        arguments={
            "mode": "search",
            "topic": query,
            "queries": [query],
        },
        proposed_by="test",
        reason="test search proposal",
    )


def assert_action_evidence(
    result: Any,
    expected_capability_id: str,
    expected_status: str,
) -> None:
    """Assert that an :class:`ActionProposalView` has the expected shape."""
    assert result.capability_id == expected_capability_id
    assert result.status == expected_status
    if expected_status == "success":
        assert result.execution is not None
        assert result.execution.get("status") == "success"
        assert result.execution.get("result") is not None
