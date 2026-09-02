from __future__ import annotations

import base64
import os
import sqlite3
import stat

import pytest
from backend.app.core.settings import Settings
from backend.app.services.llm_provider_profiles import (
    BUILTIN_MANAGED_PROFILE_ID,
    LEGACY_EXTERNAL_PROFILE_ID,
    LLMProviderProfileStore,
    ProviderConfigError,
    SecretStoreLockedError,
)


def _store(tmp_path, monkeypatch) -> LLMProviderProfileStore:
    monkeypatch.delenv("JARVIS_SECRET_STORE_KEY", raising=False)
    monkeypatch.delenv("JARVIS_SECRET_STORE_PREVIOUS_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("KEEP=value\n", encoding="utf-8")
    return LLMProviderProfileStore(tmp_path / "operator.sqlite", env_path)


def _create(
    store: LLMProviderProfileStore,
    *,
    name: str = "Lab server",
    kind: str = "openai_compatible",
    endpoint: str | None = "http://127.0.0.1:8888",
    api_key: str | None = None,
):
    return store.create_profile(
        name=name,
        kind=kind,
        endpoint=endpoint,
        model="test-model",
        context_window=8192,
        timeout_seconds=30,
        api_key=api_key,
    )


def test_profile_crud_normalizes_compatible_endpoint_and_protects_selection(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    profile = _create(store)

    assert profile.endpoint == "http://127.0.0.1:8888/v1"
    with pytest.raises(ProviderConfigError, match="already exists"):
        _create(store, name="lab SERVER")

    updated = store.update_profile(
        profile.profile_id,
        name="Unsloth",
        kind="openai_compatible",
        endpoint="http://127.0.0.1:8888/v1",
        model="unsloth/model",
        context_window=32768,
        timeout_seconds=90,
    )
    assert (updated.name, updated.model, updated.context_window) == ("Unsloth", "unsloth/model", 32768)

    selection = store.set_selection(
        primary_profile_id=updated.profile_id,
        local_fallback_profile_id=BUILTIN_MANAGED_PROFILE_ID,
        cloud_escalation_enabled=False,
        cloud_profile_id=None,
    )
    assert selection.persisted is True
    with pytest.raises(ProviderConfigError, match="selected"):
        store.delete_profile(updated.profile_id)


@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        ("http://example.com", "require HTTPS"),
        ("https://user:pass@example.com", "credentials"),
        ("https://example.com/v1?key=value", "query"),
        ("ftp://127.0.0.1", "HTTP"),
        ("http://127.0.0.1:8888/custom", "empty or /v1"),
    ],
)
def test_profile_endpoint_validation(tmp_path, monkeypatch, endpoint, message):
    store = _store(tmp_path, monkeypatch)
    with pytest.raises(ProviderConfigError, match=message):
        _create(store, endpoint=endpoint)


def test_cloud_selection_constraints(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    local = _create(store)
    cloud = _create(
        store,
        name="OpenAI",
        kind="openai",
        endpoint=None,
        api_key="secret-token",
    )

    selection = store.set_selection(
        primary_profile_id=local.profile_id,
        local_fallback_profile_id=BUILTIN_MANAGED_PROFILE_ID,
        cloud_escalation_enabled=True,
        cloud_profile_id=cloud.profile_id,
    )
    assert selection.cloud_profile_id == cloud.profile_id
    disabled = store.set_selection(
        primary_profile_id=local.profile_id,
        local_fallback_profile_id=BUILTIN_MANAGED_PROFILE_ID,
        cloud_escalation_enabled=False,
        cloud_profile_id=cloud.profile_id,
    )
    assert disabled.cloud_escalation_enabled is False
    assert disabled.cloud_profile_id == cloud.profile_id
    with pytest.raises(ProviderConfigError, match="local primary"):
        store.set_selection(
            primary_profile_id=cloud.profile_id,
            local_fallback_profile_id=None,
            cloud_escalation_enabled=True,
            cloud_profile_id=cloud.profile_id,
        )


def test_secret_storage_encrypts_replaces_deletes_and_rotates(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    profile = _create(store, api_key="first-plaintext-secret")
    database_bytes = store.db_path.read_bytes()
    assert b"first-plaintext-secret" not in database_bytes
    assert profile.has_secret is True
    assert profile.readiness_state == "configured"

    with sqlite3.connect(store.db_path) as connection:
        first_nonce = connection.execute("SELECT nonce FROM operator_secret").fetchone()[0]
    store.write_secret(profile.profile_id, "api_key", "replacement-secret")
    with sqlite3.connect(store.db_path) as connection:
        second_nonce = connection.execute("SELECT nonce FROM operator_secret").fetchone()[0]
    assert first_nonce != second_nonce
    assert store.read_secret(profile.profile_id, "api_key") == "replacement-secret"

    old_key = store.env_path.read_text(encoding="utf-8").split("JARVIS_SECRET_STORE_KEY=", 1)[1].splitlines()[0]
    store.rotate_key()
    new_key = store.env_path.read_text(encoding="utf-8").split("JARVIS_SECRET_STORE_KEY=", 1)[1].splitlines()[0]
    assert old_key != new_key
    assert store.read_secret(profile.profile_id, "api_key") == "replacement-secret"
    assert "JARVIS_SECRET_STORE_PREVIOUS_KEY" not in store.env_path.read_text(encoding="utf-8")

    store.delete_secret(profile.profile_id, "api_key")
    assert store.read_secret(profile.profile_id, "api_key") is None
    assert store.get_profile(profile.profile_id).has_secret is False


def test_secret_rows_lock_when_key_is_missing(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    profile = _create(store, api_key="secret")
    store.env_path.write_text("KEEP=value\n", encoding="utf-8")
    monkeypatch.delenv("JARVIS_SECRET_STORE_KEY", raising=False)

    with pytest.raises(SecretStoreLockedError, match="unavailable"):
        store.read_secret(profile.profile_id, "api_key")
    with pytest.raises(SecretStoreLockedError, match="unavailable"):
        store.write_secret(profile.profile_id, "api_key", "new-secret")


def test_rotation_rejects_process_environment_key_override(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    _create(store, api_key="secret")
    override = base64.urlsafe_b64encode(b"x" * 32).decode("ascii")
    monkeypatch.setenv("JARVIS_SECRET_STORE_KEY", override)

    with pytest.raises(SecretStoreLockedError, match=r"outside \.env"):
        store.rotate_key()


def test_store_resumes_interrupted_rotation(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    profile = _create(store, api_key="survives-rotation")
    old_key = store.env_path.read_text(encoding="utf-8").split("JARVIS_SECRET_STORE_KEY=", 1)[1].splitlines()[0]
    new_key = base64.urlsafe_b64encode(b"n" * 32).decode("ascii")
    store.env_path.write_text(
        f"KEEP=value\nJARVIS_SECRET_STORE_KEY={new_key}\nJARVIS_SECRET_STORE_PREVIOUS_KEY={old_key}\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("JARVIS_SECRET_STORE_KEY", raising=False)
    monkeypatch.delenv("JARVIS_SECRET_STORE_PREVIOUS_KEY", raising=False)

    recovered = LLMProviderProfileStore(store.db_path, store.env_path)

    assert recovered.read_secret(profile.profile_id, "api_key") == "survives-rotation"
    assert "JARVIS_SECRET_STORE_PREVIOUS_KEY" not in recovered.env_path.read_text(encoding="utf-8")


def test_store_opens_initialized_database_without_schema_write(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    db_path = store.db_path
    env_path = store.env_path
    os.chmod(db_path, stat.S_IREAD)
    try:
        reopened = LLMProviderProfileStore(db_path, env_path)
        assert reopened.selection_persisted() is False
    finally:
        os.chmod(db_path, stat.S_IREAD | stat.S_IWRITE)


def test_store_refuses_rotation_recovery_with_process_key_override(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    _create(store, api_key="secret")
    old_key = store.env_path.read_text(encoding="utf-8").split("JARVIS_SECRET_STORE_KEY=", 1)[1].splitlines()[0]
    new_key = base64.urlsafe_b64encode(b"n" * 32).decode("ascii")
    override = base64.urlsafe_b64encode(b"x" * 32).decode("ascii")
    store.env_path.write_text(
        f"JARVIS_SECRET_STORE_KEY={new_key}\nJARVIS_SECRET_STORE_PREVIOUS_KEY={old_key}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JARVIS_SECRET_STORE_KEY", override)

    with pytest.raises(SecretStoreLockedError, match="cannot resume"):
        LLMProviderProfileStore(store.db_path, store.env_path)


def test_profile_bound_authenticated_metadata_rejects_ciphertext_swap(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    first = _create(store, name="First", api_key="first-secret")
    second = _create(store, name="Second", api_key="second-secret")
    with sqlite3.connect(store.db_path) as connection:
        second_row = connection.execute(
            "SELECT nonce, ciphertext FROM operator_secret WHERE owner_id = ?",
            (second.profile_id,),
        ).fetchone()
        connection.execute(
            "UPDATE operator_secret SET nonce = ?, ciphertext = ? WHERE owner_id = ?",
            (second_row[0], second_row[1], first.profile_id),
        )

    with pytest.raises(SecretStoreLockedError, match="cannot decrypt"):
        store.read_secret(first.profile_id, "api_key")


def test_legacy_external_env_profile_uses_model_name_context_and_persists_selection(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    settings = Settings(
        use_local_model=True,
        llama_cpp_managed_explicit=True,
        llama_cpp_managed=False,
        llama_cpp_base_url_explicit=True,
        llama_cpp_base_url="http://127.0.0.1:8888/v1",
        llama_cpp_model_name="unsloth-model",
        llama_cpp_context_size=65536,
    )

    profile = store.get_profile(LEGACY_EXTERNAL_PROFILE_ID, settings)
    assert (profile.model, profile.context_window, profile.endpoint) == (
        "unsloth-model",
        65536,
        "http://127.0.0.1:8888/v1",
    )
    selection = store.set_selection(
        primary_profile_id=LEGACY_EXTERNAL_PROFILE_ID,
        local_fallback_profile_id=None,
        cloud_escalation_enabled=False,
        cloud_profile_id=None,
        settings=settings,
    )
    assert selection.primary_profile_id == LEGACY_EXTERNAL_PROFILE_ID
    assert store.get_profile(LEGACY_EXTERNAL_PROFILE_ID).model == "unsloth-model"


def test_explicit_external_env_selection_overrides_stale_managed_selection(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    store.set_selection(
        primary_profile_id=BUILTIN_MANAGED_PROFILE_ID,
        local_fallback_profile_id=None,
        cloud_escalation_enabled=False,
        cloud_profile_id=None,
    )
    settings = Settings(
        use_local_model=True,
        llama_cpp_managed_explicit=True,
        llama_cpp_managed=False,
        llama_cpp_base_url_explicit=True,
        llama_cpp_base_url="http://127.0.0.1:8888/v1",
        llama_cpp_model_name="unsloth-model",
        llama_cpp_context_size=65536,
    )

    profiles = {profile.profile_id: profile for profile in store.list_profiles(settings)}
    selection = store.get_selection(settings)

    assert LEGACY_EXTERNAL_PROFILE_ID in profiles
    assert selection.primary_profile_id == LEGACY_EXTERNAL_PROFILE_ID
    assert selection.persisted is True
