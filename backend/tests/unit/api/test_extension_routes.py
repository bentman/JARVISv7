from __future__ import annotations

from pathlib import Path

import pytest
from backend.app.api.dependencies import get_extension_service
from backend.app.api.routes.extensions import router
from backend.app.extensions.catalog import ExtensionObservation
from backend.app.extensions.prompts import list_prompt_templates_with_errors
from backend.app.extensions.skills import list_skills_with_errors
from backend.app.extensions.store import ExtensionOverlayStore
from backend.app.services.extension_service import ExtensionService
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _seed(tmp_path: Path) -> None:
    skill = tmp_path / "extensions" / "skills" / "notes"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        "---\nname: Notes\ndescription: d\nversion: '2'\nrequested_tools: [search-public-web]\n---\nThe body.",
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts"
    prompts.mkdir(exist_ok=True)
    (prompts / "review.yaml").write_text(
        "prompt_id: review\nversion: '1'\ntitle: R\ndescription: d\nauthority: user\nbody: hello\n",
        encoding="utf-8",
    )


def _service(tmp_path: Path) -> ExtensionService:
    _seed(tmp_path)
    observed = ExtensionObservation(
        prompts=tuple(list_prompt_templates_with_errors(tmp_path).templates),
        skills=tuple(list_skills_with_errors(tmp_path).skills),
        search_providers=(("ddgs", True), ("searxng", False)),
    )
    return ExtensionService(
        observe=lambda: observed,
        store=ExtensionOverlayStore(db_path=tmp_path / "operator.sqlite"),
        config_dir=tmp_path,
        data_dir=tmp_path,
    )


def _client(service: object) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_extension_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def test_the_catalog_lists_families_with_provenance_and_trust(tmp_path: Path) -> None:
    response = _client(_service(tmp_path)).get("/extensions")

    assert response.status_code == 200
    body = response.json()
    assert body["families"] == {"prompt": 1, "search_provider": 2, "skill": 1}
    skill = next(item for item in body["extensions"] if item["extension_id"] == "skill:notes")
    assert (skill["trust"], skill["version"], skill["provenance"]) == (
        "external", "2", "data/extensions/skills",
    )


def test_a_disabled_family_member_explains_itself(tmp_path: Path) -> None:
    body = _client(_service(tmp_path)).get("/extensions/search_provider:searxng").json()

    assert body["state"] == "disabled"
    assert "Enable DDGS, SearXNG, or Tavily" in body["unavailable_explanation"]


def test_requested_tools_appear_as_an_untrusted_request(tmp_path: Path) -> None:
    body = _client(_service(tmp_path)).get("/extensions/skill:notes").json()

    assert body["dependencies"] == ["search-public-web"]
    assert body["metadata_claims"]["requested_capabilities"]["trusted"] is False


def test_bodies_are_served_only_on_request(tmp_path: Path) -> None:
    client = _client(_service(tmp_path))

    listing = client.get("/extensions").text
    assert "The body." not in listing

    assert client.get("/extensions/skill:notes/body").json()["body"].strip() == "The body."
    assert client.get("/extensions/search_provider:ddgs/body").status_code == 404


def test_state_changes_round_trip_and_conflict_on_a_stale_revision(tmp_path: Path) -> None:
    client = _client(_service(tmp_path))

    first = client.post("/extensions/skill:notes/state", json={"state": "disabled", "reason": "not vetted"})
    assert first.status_code == 200
    assert first.json()["state"] == "disabled"
    assert first.json()["revision"] == 1

    stale = client.post(
        "/extensions/skill:notes/state", json={"state": "enabled", "expected_revision": 99}
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["current_revision"] == 1


def test_a_retired_extension_cannot_be_revived(tmp_path: Path) -> None:
    client = _client(_service(tmp_path))
    client.post("/extensions/skill:notes/state", json={"state": "retired"})

    response = client.post(
        "/extensions/skill:notes/state", json={"state": "enabled", "expected_revision": 1}
    )

    assert response.status_code == 422
    assert "retired" in response.json()["detail"]["message"]


def test_unknown_extensions_and_states_are_refused(tmp_path: Path) -> None:
    client = _client(_service(tmp_path))

    assert client.get("/extensions/skill:nope").status_code == 404
    assert client.post("/extensions/skill:notes/state", json={"state": "banished"}).status_code == 422
    assert client.post("/extensions/skill:notes/state", json={"state": "enabled", "oops": 1}).status_code == 422


def test_load_errors_are_listed_separately(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "prompts" / "broken.yaml").write_text(
        "prompt_id: broken\nversion: '1'\ntitle: B\ndescription: d\nauthority: application\nbody: x\n",
        encoding="utf-8",
    )
    observed = ExtensionObservation(
        prompts=tuple(list_prompt_templates_with_errors(tmp_path).templates),
        prompt_errors=tuple(list_prompt_templates_with_errors(tmp_path).errors),
    )
    service = ExtensionService(
        observe=lambda: observed,
        store=ExtensionOverlayStore(db_path=tmp_path / "operator.sqlite"),
        config_dir=tmp_path,
        data_dir=tmp_path,
    )

    body = _client(service).get("/extensions/errors").json()

    assert body["errors"][0]["family"] == "prompt"
    assert "authority must be one of" in body["errors"][0]["reason"]


def test_unexpected_failures_return_a_sanitized_500() -> None:
    class _ExplodingService:
        def catalog(self):
            raise RuntimeError("C:/private/state.sqlite exploded")

    response = _client(_ExplodingService()).get("/extensions")

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "error": "internal_error",
        "message": "extension operation failed",
    }
    assert "C:/private" not in response.text


@pytest.mark.parametrize("path", ["/extensions", "/extensions/errors"])
def test_routes_report_unavailability_rather_than_failing_opaquely(path: str) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(path)

    assert response.status_code == 503
    assert response.json()["detail"]["message"] == "extension service is unavailable"
