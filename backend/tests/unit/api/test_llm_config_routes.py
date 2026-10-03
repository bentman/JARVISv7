from __future__ import annotations

from types import SimpleNamespace

from backend.app.actions.catalog import CapabilityObservation
from backend.app.api.app import install_capability_error_handler
from backend.app.api.routes import llm_config
from backend.app.services.capability_service import CapabilityService
from backend.app.services.llm_provider_profiles import LLMProviderProfileStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> tuple[TestClient, LLMProviderProfileStore]:
    monkeypatch.delenv("JARVIS_SECRET_STORE_KEY", raising=False)
    monkeypatch.delenv("JARVIS_SECRET_STORE_PREVIOUS_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("KEEP=value\n", encoding="utf-8")
    store = LLMProviderProfileStore(tmp_path / "operator.sqlite", env_path)
    monkeypatch.setattr(llm_config, "PROFILE_STORE_FACTORY", lambda: store)
    app = FastAPI()
    install_capability_error_handler(app)
    app.include_router(llm_config.router)
    return TestClient(app), store


def test_llm_profile_api_masks_secret_and_enforces_selected_delete(tmp_path, monkeypatch):
    client, _store = _client(tmp_path, monkeypatch)
    created = client.post(
        "/config/llm/profiles",
        json={
            "name": "OpenAI",
            "kind": "openai",
            "model": "gpt-test",
            "context_window": 128000,
            "timeout_seconds": 45,
            "api_key": "api-secret-value",
        },
    )

    assert created.status_code == 200
    profile = created.json()
    assert profile["has_secret"] is True
    assert profile["readiness_state"] == "configured"
    assert "api-secret-value" not in created.text
    assert "ciphertext" not in created.text

    configured = client.get("/config/llm").json()
    assert configured["selection"]["persisted"] is False
    assert all("api_key" not in item for item in configured["profiles"])

    selected = client.put(
        "/config/llm/selection",
        json={
            "primary_profile_id": profile["profile_id"],
            "cloud_escalation_enabled": False,
        },
    )
    assert selected.status_code == 200
    assert selected.json()["persisted"] is True
    rejected = client.delete(f"/config/llm/profiles/{profile['profile_id']}")
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["error"] == "invalid_provider_configuration"
    assert "api-secret-value" not in rejected.text


def test_llm_profile_api_authorizes_full_profile_payload_with_capability_service(tmp_path, monkeypatch):
    client, store = _client(tmp_path, monkeypatch)
    capability_service = CapabilityService(
        observe=lambda: CapabilityObservation(provider_store_present=True)
    )
    client.app.state.jarvis_state = SimpleNamespace(capability_service=capability_service)  # type: ignore[attr-defined]

    created = client.post(
        "/config/llm/profiles",
        json={
            "name": "Local Qwen",
            "kind": "openai_compatible",
            "endpoint": "http://127.0.0.1:8888/v1",
            "model": "qwen2.5-gpro-gsm8k-rtx3060",
            "context_window": 32768,
            "timeout_seconds": 60,
            "api_key": "api-secret-value",
        },
    )

    assert created.status_code == 200
    profile = created.json()
    assert profile["name"] == "Local Qwen"
    assert profile["profile_id"] in {item.profile_id for item in store.list_profiles()}
    audit = capability_service.audit(limit=10).records
    proposal = next(item for item in audit if item["kind"] == "action_proposal")
    assert proposal["record"]["arguments"]["api_key"] == "***"
    assert proposal["record"]["arguments"]["endpoint"] == "http://127.0.0.1:8888/v1"

    # The capability's own argument schema refuses this before the store sees it; the operator
    # must get that reason, not a bare 500.
    refused = client.put(
        f"/config/llm/profiles/{profile['profile_id']}",
        json={
            "name": "Local Qwen",
            "kind": "openai_compatible",
            "endpoint": "http://127.0.0.1:8888/v1",
            "model": "qwen2.5-gpro-gsm8k-rtx3060",
            "context_window": 32768,
            "timeout_seconds": 0,
        },
    )
    assert refused.status_code == 403
    assert "timeout_seconds" in refused.json()["detail"]["message"]


def test_llm_profile_api_supports_secret_delete_discovery_and_rotation(tmp_path, monkeypatch):
    client, store = _client(tmp_path, monkeypatch)
    capability_service = CapabilityService(
        observe=lambda: CapabilityObservation(provider_store_present=True)
    )
    client.app.state.jarvis_state = SimpleNamespace(capability_service=capability_service)  # type: ignore[attr-defined]
    created = client.post(
        "/config/llm/profiles",
        json={
            "name": "Lab",
            "kind": "openai_compatible",
            "endpoint": "http://127.0.0.1:8888",
            "model": "manual-model",
            "context_window": 8192,
            "timeout_seconds": 30,
            "api_key": "optional-secret",
        },
    ).json()
    monkeypatch.setattr(
        llm_config,
        "provider_model_discovery",
        lambda profile_store, profile, api_key=None: [{"id": "discovered", "context_window": 32768}],
    )

    tested = client.post(f"/config/llm/profiles/{created['profile_id']}/test")
    assert tested.status_code == 200
    assert tested.json()["models"] == [
        {"id": "discovered", "display_name": None, "context_window": 32768}
    ]
    # The connectivity test is an outbound read and leaves evidence like any other action.
    executions = [
        item
        for item in capability_service.audit(limit=50).records
        if item["capability_id"] == "provider-connectivity-test"
        and item["kind"] == "execution_result"
    ]
    assert [item["record"]["status"] for item in executions] == ["success"]
    assert executions[0]["record"]["result"]["status"] == "ready"
    updated = client.put(
        f"/config/llm/profiles/{created['profile_id']}",
        json={
            "name": "Lab",
            "kind": "openai_compatible",
            "endpoint": "http://127.0.0.1:8888/v1",
            "model": "discovered",
            "context_window": 32768,
            "timeout_seconds": 30,
            "clear_api_key": True,
        },
    )
    assert updated.json()["has_secret"] is False
    assert store.read_secret(created["profile_id"], "api_key") is None
    rotated = client.post("/config/secrets/rotate")
    assert rotated.status_code == 200
    assert rotated.json() == {"rotated": True}

    # Verify selection update passes capability validation with all required/optional args
    selected = client.put(
        "/config/llm/selection",
        json={
            "primary_profile_id": created["profile_id"],
            "local_fallback_profile_id": None,
            "cloud_escalation_enabled": False,
            "cloud_profile_id": None,
        },
    )
    assert selected.status_code == 200
    assert selected.json()["primary_profile_id"] == created["profile_id"]
    selection_execs = [
        item
        for item in capability_service.audit(limit=50).records
        if item["capability_id"] == "provider-selection-update"
        and item["kind"] == "execution_result"
    ]
    assert [item["record"]["status"] for item in selection_execs] == ["success"]

    # Verify draft connectivity test passes capability validation with draft parameters
    draft_tested = client.post(
        f"/config/llm/profiles/{created['profile_id']}/test",
        json={
            "name": "Draft Ollama",
            "kind": "ollama",
            "endpoint": "http://127.0.0.1:11434",
            "model": "llama3.2",
            "context_window": 8192,
            "timeout_seconds": 30.0,
        },
    )
    assert draft_tested.status_code == 200
    assert draft_tested.json()["status"] == "ready"
    draft_execs = [
        item
        for item in capability_service.audit(limit=50).records
        if item["capability_id"] == "provider-connectivity-test"
        and item["kind"] == "execution_result"
    ]
    assert [item["record"]["status"] for item in draft_execs] == ["success", "success"]


def test_llm_profile_test_returns_sanitized_unverified_result(tmp_path, monkeypatch):
    client, _store = _client(tmp_path, monkeypatch)
    profile = client.post(
        "/config/llm/profiles",
        json={
            "name": "Anthropic",
            "kind": "anthropic",
            "model": "claude-test",
            "context_window": 200000,
            "timeout_seconds": 30,
        },
    ).json()

    tested = client.post(f"/config/llm/profiles/{profile['profile_id']}/test")
    assert tested.status_code == 200
    assert tested.json() == {
        "status": "unverified",
        "reason": "provider credential is not configured",
        "models": [],
    }


def test_llm_profile_test_supports_draft_payload_for_new_and_override(tmp_path, monkeypatch):
    client, _store = _client(tmp_path, monkeypatch)
    discovered = []

    def fake_discovery(store, profile, api_key=None):
        discovered.append((profile.kind, profile.endpoint, profile.name, api_key))
        return [{"id": f"model-for-{profile.kind}", "context_window": 8192}]

    monkeypatch.setattr(llm_config, "provider_model_discovery", fake_discovery)

    # 1. Test draft payload on "new" profile ID
    tested_new = client.post(
        "/config/llm/profiles/new/test",
        json={
            "name": "Ollama Local",
            "kind": "ollama",
            "endpoint": "http://127.0.0.1:11434",
        },
    )
    assert tested_new.status_code == 200
    assert tested_new.json()["status"] == "ready"
    assert tested_new.json()["models"] == [{"id": "model-for-ollama", "display_name": None, "context_window": 8192}]
    assert discovered[-1] == ("ollama", "http://127.0.0.1:11434", "Ollama Local", "")

    # 2. Test draft payload overriding existing saved profile
    created = client.post(
        "/config/llm/profiles",
        json={
            "name": "llama.cpp Local",
            "kind": "openai_compatible",
            "endpoint": "http://127.0.0.1:8080/v1",
            "model": "qwen",
            "context_window": 8192,
            "timeout_seconds": 30,
            "api_key": "stored-secret",
        },
    ).json()

    tested_override = client.post(
        f"/config/llm/profiles/{created['profile_id']}/test",
        json={
            "kind": "ollama",
            "endpoint": "http://127.0.0.1:11434",
        },
    )
    assert tested_override.status_code == 200
    assert tested_override.json()["status"] == "ready"
    # A stored credential is not forwarded to an overridden endpoint.
    assert discovered[-1] == ("ollama", "http://127.0.0.1:11434", "llama.cpp Local", "")

    # A built-in managed profile reports readiness and ignores draft overrides.
    calls = len(discovered)
    managed = client.post(
        "/config/llm/profiles/builtin:managed-llama-cpp/test",
        json={"kind": "ollama", "endpoint": "http://127.0.0.1:11434"},
    )
    assert managed.json()["status"] == "configured"
    assert len(discovered) == calls
