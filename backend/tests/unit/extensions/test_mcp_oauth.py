"""Tests for MCP OAuth credential management."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from backend.app.extensions.mcp import McpConnectionDefinition
from backend.app.extensions.mcp_oauth import (
    McpOAuthConfig,
    McpOAuthFlow,
    McpOAuthToken,
    config_from_definition,
    discover_authorization_server,
    load_oauth_token,
    parse_resource_metadata_url,
    protected_resource_metadata_url,
    resolve_oauth_bearer,
    save_oauth_token,
)
from backend.app.services.extension_runtime_service import ExtensionRuntimeService


def _valid_oauth_config(**overrides: object) -> McpOAuthConfig:
    defaults: dict[str, object] = {
        "authorization_url": "https://auth.example.com/authorize",
        "token_url": "https://auth.example.com/token",
        "client_id": "test-client",
        "scopes": ("read", "write"),
    }
    defaults.update(overrides)
    return McpOAuthConfig(**defaults)  # type: ignore[arg-type]


def _valid_token(**overrides: object) -> McpOAuthToken:
    defaults: dict[str, object] = {
        "access_token": "test-access-token",
        "token_type": "Bearer",
        "refresh_token": "test-refresh-token",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "scope": "read write",
    }
    defaults.update(overrides)
    return McpOAuthToken(**defaults)  # type: ignore[arg-type]


class TestMcpOAuthConfig:
    def test_valid_config(self) -> None:
        config = _valid_oauth_config()
        assert config.authorization_url == "https://auth.example.com/authorize"
        assert config.client_id == "test-client"
        assert config.redirect_port == 19823
        assert config.pkce is True

    def test_invalid_authorization_url_http(self) -> None:
        with pytest.raises(ValueError, match="authorization_url must be a valid HTTPS URL"):
            _valid_oauth_config(authorization_url="http://auth.example.com/authorize")

    def test_invalid_authorization_url_no_scheme(self) -> None:
        with pytest.raises(ValueError, match="authorization_url must be a valid HTTPS URL"):
            _valid_oauth_config(authorization_url="auth.example.com/authorize")

    def test_invalid_token_url(self) -> None:
        with pytest.raises(ValueError, match="token_url must be a valid HTTPS URL"):
            _valid_oauth_config(token_url="ftp://auth.example.com/token")

    def test_empty_client_id(self) -> None:
        with pytest.raises(ValueError, match="client_id must be non-empty"):
            _valid_oauth_config(client_id="")

    def test_invalid_scopes(self) -> None:
        with pytest.raises(ValueError, match="scopes entries must be non-empty strings"):
            _valid_oauth_config(scopes=("read", ""))

    def test_invalid_redirect_port_low(self) -> None:
        with pytest.raises(ValueError, match="redirect_port must be between"):
            _valid_oauth_config(redirect_port=80)

    def test_invalid_redirect_port_high(self) -> None:
        with pytest.raises(ValueError, match="redirect_port must be between"):
            _valid_oauth_config(redirect_port=70000)

    def test_custom_redirect_port(self) -> None:
        config = _valid_oauth_config(redirect_port=8080)
        assert config.redirect_port == 8080


class TestMcpOAuthToken:
    def test_token_creation(self) -> None:
        token = _valid_token()
        assert token.access_token == "test-access-token"
        assert token.token_type == "Bearer"
        assert token.refresh_token == "test-refresh-token"

    def test_is_expired_false(self) -> None:
        token = _valid_token(
            expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat()
        )
        assert token.is_expired() is False

    def test_is_expired_true(self) -> None:
        token = _valid_token(
            expires_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat()
        )
        assert token.is_expired() is True

    def test_is_expired_none(self) -> None:
        token = _valid_token(expires_at=None)
        assert token.is_expired() is False

    def test_to_dict(self) -> None:
        token = _valid_token()
        d = token.to_dict()
        assert d["access_token"] == "test-access-token"
        assert d["token_type"] == "Bearer"


class TestMcpOAuthFlow:
    def test_start_authorization_generates_url_with_state(self) -> None:
        config = _valid_oauth_config()
        flow = McpOAuthFlow(config)
        url, state = flow.start_authorization()
        assert "https://auth.example.com/authorize" in url
        assert "response_type=code" in url
        assert "client_id=test-client" in url
        assert "state=" in url
        assert state  # non-empty

    def test_start_authorization_with_pkce(self) -> None:
        config = _valid_oauth_config(pkce=True)
        flow = McpOAuthFlow(config)
        url, state = flow.start_authorization()
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url
        # The verifier is held on the host, never carried through the browser.
        assert state not in url.split("code_challenge=")[1]
        assert "code_verifier" not in url
        assert f"state={state}" in url

    def test_start_authorization_without_pkce(self) -> None:
        config = _valid_oauth_config(pkce=False)
        flow = McpOAuthFlow(config)
        url, state = flow.start_authorization()
        assert "code_challenge=" not in url
        assert f"state={state}" in url

    def test_exchange_code_rejects_an_unissued_state(self) -> None:
        flow = McpOAuthFlow(_valid_oauth_config())
        with pytest.raises(ValueError, match="unknown or already used"):
            flow.exchange_code("auth-code", "never-issued")

    def test_exchange_code_rejects_a_replayed_state(self) -> None:
        flow = McpOAuthFlow(_valid_oauth_config())
        _, state = flow.start_authorization()
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"access_token": "t"}).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            flow.exchange_code("auth-code", state)
        with pytest.raises(ValueError, match="unknown or already used"):
            flow.exchange_code("auth-code", state)

    def test_exchange_code_constructs_correct_request(self) -> None:
        config = _valid_oauth_config()
        flow = McpOAuthFlow(config)
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "access_token": "new-token",
            "token_type": "Bearer",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "scope": "read write",
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        _, state = flow.start_authorization()
        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            token = flow.exchange_code("auth-code", state)
            assert token.access_token == "new-token"
            assert token.refresh_token == "new-refresh"
            call_args = mock_urlopen.call_args[0][0]
            assert call_args.get_method() == "POST"
            body = call_args.data.decode("utf-8")
            assert "grant_type=authorization_code" in body
            assert "code=auth-code" in body
            # The flow supplies the verifier it minted; the caller never handles it.
            assert "code_verifier=" in body

    def test_refresh_token_constructs_correct_request(self) -> None:
        config = _valid_oauth_config()
        flow = McpOAuthFlow(config)
        old_token = _valid_token()
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "access_token": "refreshed-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "read write",
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            new_token = flow.refresh_token(old_token)
            assert new_token.access_token == "refreshed-token"
            call_args = mock_urlopen.call_args[0][0]
            body = call_args.data.decode("utf-8")
            assert "grant_type=refresh_token" in body
            assert "refresh_token=test-refresh-token" in body

    def test_refresh_token_without_refresh_token_raises(self) -> None:
        config = _valid_oauth_config()
        flow = McpOAuthFlow(config)
        token = _valid_token(refresh_token=None)
        with pytest.raises(ValueError, match="no refresh_token"):
            flow.refresh_token(token)


class _FakeSecretStore:
    """Stands in for the application's encrypted operator secret store."""

    def __init__(self) -> None:
        self.secrets: dict[tuple[str, str], str] = {}

    def write_secret(self, owner_id: str, secret_name: str, value: str) -> None:
        self.secrets[(owner_id, secret_name)] = value

    def read_secret(self, owner_id: str, secret_name: str) -> str | None:
        return self.secrets.get((owner_id, secret_name))


class TestOAuthTokenPersistence:
    def test_a_saved_token_round_trips_through_the_secret_store(self) -> None:
        store = _FakeSecretStore()
        save_oauth_token(store, "test-conn", _valid_token())
        loaded = load_oauth_token(store, "test-conn")
        assert loaded is not None
        assert loaded.access_token == "test-access-token"
        assert loaded.refresh_token == "test-refresh-token"

    def test_tokens_are_namespaced_per_connection(self) -> None:
        store = _FakeSecretStore()
        save_oauth_token(store, "conn-a", _valid_token())
        assert load_oauth_token(store, "conn-b") is None

    def test_an_unauthorized_connection_is_reported_not_silently_unauthenticated(self) -> None:
        oauth = {
            "authorization_url": "https://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            "client_id": "test-client",
        }
        with pytest.raises(ValueError, match="not authorized"):
            resolve_oauth_bearer(_FakeSecretStore(), "test-conn", oauth)

    def test_an_unexpired_token_is_used_without_refreshing(self) -> None:
        store = _FakeSecretStore()
        save_oauth_token(store, "test-conn", _valid_token())
        oauth = {
            "authorization_url": "https://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            "client_id": "test-client",
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            assert resolve_oauth_bearer(store, "test-conn", oauth) == "test-access-token"
        mock_urlopen.assert_not_called()

    def test_an_expired_token_is_refreshed_and_written_back(self) -> None:
        store = _FakeSecretStore()
        expired = _valid_token(
            expires_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat()
        )
        save_oauth_token(store, "test-conn", expired)
        oauth = {
            "authorization_url": "https://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            "client_id": "test-client",
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "access_token": "refreshed-token",
            "expires_in": 3600,
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            assert resolve_oauth_bearer(store, "test-conn", oauth) == "refreshed-token"
        assert load_oauth_token(store, "test-conn").access_token == "refreshed-token"  # type: ignore[union-attr]

    def test_an_expired_token_without_a_refresh_token_requires_reconnection(self) -> None:
        store = _FakeSecretStore()
        save_oauth_token(store, "test-conn", _valid_token(
            refresh_token=None,
            expires_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        ))
        oauth = {
            "authorization_url": "https://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            "client_id": "test-client",
        }
        with pytest.raises(ValueError, match="reconnect"):
            resolve_oauth_bearer(store, "test-conn", oauth)


class TestAuthorizationServerDiscovery:
    def test_the_well_known_url_preserves_the_resource_path(self) -> None:
        assert protected_resource_metadata_url("https://mcp.example.test/mcp") == (
            "https://mcp.example.test/.well-known/oauth-protected-resource/mcp"
        )

    def test_a_challenge_header_yields_the_metadata_url(self) -> None:
        header = 'Bearer error="invalid_token", resource_metadata="https://a.test/.well-known/x"'
        assert parse_resource_metadata_url(header) == "https://a.test/.well-known/x"

    def test_a_challenge_without_metadata_yields_none(self) -> None:
        assert parse_resource_metadata_url('Bearer error="invalid_token"') is None

    def test_discovery_follows_metadata_to_the_authorization_endpoints(self) -> None:
        pages = {
            "https://mcp.example.test/.well-known/oauth-protected-resource/mcp": {
                "resource": "https://mcp.example.test/mcp",
                "authorization_servers": ["https://auth.example.test"],
                "scopes_supported": ["read"],
            },
            "https://auth.example.test/.well-known/oauth-authorization-server": {
                "authorization_endpoint": "https://auth.example.test/authorize",
                "token_endpoint": "https://auth.example.test/token",
            },
        }
        with patch("backend.app.extensions.mcp_oauth._fetch_json", side_effect=lambda url: pages[url]):
            found = discover_authorization_server("https://mcp.example.test/mcp")
        assert found["authorization_url"] == "https://auth.example.test/authorize"
        assert found["token_url"] == "https://auth.example.test/token"

    def test_metadata_without_an_authorization_server_is_refused(self) -> None:
        with (
            patch("backend.app.extensions.mcp_oauth._fetch_json", return_value={}),
            pytest.raises(ValueError, match="no authorization server"),
        ):
            discover_authorization_server("https://mcp.example.test/mcp")

    def test_a_definition_without_endpoints_discovers_them(self) -> None:
        with patch(
            "backend.app.extensions.mcp_oauth.discover_authorization_server",
            return_value={
                "authorization_url": "https://auth.example.test/authorize",
                "token_url": "https://auth.example.test/token",
                "scopes_supported": ("read",),
                "resource": "https://mcp.example.test/mcp",
            },
        ):
            config = config_from_definition(
                {"client_id": "c"}, resource_url="https://mcp.example.test/mcp"
            )
        assert config.token_url == "https://auth.example.test/token"
        assert config.resource == "https://mcp.example.test/mcp"

    def test_an_explicit_endpoint_overrides_discovery(self) -> None:
        with patch("backend.app.extensions.mcp_oauth.discover_authorization_server") as discover:
            config = config_from_definition({
                "client_id": "c",
                "authorization_url": "https://auth.example.com/authorize",
                "token_url": "https://auth.example.com/token",
            })
        discover.assert_not_called()
        assert config.token_url == "https://auth.example.com/token"


class TestResourceBoundTokens:
    def test_the_resource_parameter_is_sent_on_every_token_leg(self) -> None:
        config = _valid_oauth_config(resource="https://mcp.example.test/mcp")
        flow = McpOAuthFlow(config)
        url, state = flow.start_authorization()
        assert "resource=https%3A%2F%2Fmcp.example.test%2Fmcp" in url
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "access_token": "t", "refresh_token": "r",
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            token = flow.exchange_code("auth-code", state)
            assert "resource=https" in mock_urlopen.call_args[0][0].data.decode("utf-8")
            flow.refresh_token(token)
            assert "resource=https" in mock_urlopen.call_args[0][0].data.decode("utf-8")

    def test_a_non_http_resource_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="resource must be a valid HTTP"):
            _valid_oauth_config(resource="not-a-url")


class TestMcpConnectionDefinitionOAuth:
    def _valid_mapping(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "transport": "streamable_http",
            "url": "https://mcp.example.test/mcp",
        }
        base.update(overrides)
        return base

    def test_valid_oauth_config(self) -> None:
        oauth = {
            "authorization_url": "https://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            "client_id": "my-client",
            "scopes": ["read"],
        }
        defn = McpConnectionDefinition.from_mapping("test", self._valid_mapping(oauth=oauth))
        assert defn.oauth == oauth

    def test_oauth_missing_required_field(self) -> None:
        oauth = {
            "authorization_url": "https://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            # missing client_id
        }
        with pytest.raises(ValueError, match="oauth requires client_id"):
            McpConnectionDefinition.from_mapping("test", self._valid_mapping(oauth=oauth))

    def test_oauth_invalid_url(self) -> None:
        oauth = {
            "authorization_url": "http://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            "client_id": "my-client",
        }
        with pytest.raises(ValueError, match=re.escape("oauth.authorization_url must be a valid HTTPS URL")):
            McpConnectionDefinition.from_mapping("test", self._valid_mapping(oauth=oauth))

    def test_oauth_empty_client_id(self) -> None:
        oauth = {
            "authorization_url": "https://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            "client_id": "",
        }
        with pytest.raises(ValueError, match=re.escape("oauth.client_id must be a non-empty string")):
            McpConnectionDefinition.from_mapping("test", self._valid_mapping(oauth=oauth))

    def test_oauth_invalid_scopes(self) -> None:
        oauth = {
            "authorization_url": "https://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            "client_id": "my-client",
            "scopes": [""],
        }
        with pytest.raises(ValueError, match=re.escape("oauth.scopes must be a list of non-empty strings")):
            McpConnectionDefinition.from_mapping("test", self._valid_mapping(oauth=oauth))

    def test_oauth_none_is_valid(self) -> None:
        defn = McpConnectionDefinition.from_mapping("test", self._valid_mapping())
        assert defn.oauth is None

    def test_oauth_not_mapping_raises(self) -> None:
        with pytest.raises(ValueError, match="oauth must be a mapping"):
            McpConnectionDefinition.from_mapping("test", self._valid_mapping(oauth="not-a-dict"))


class TestMcpCredentialResolution:
    """The host resolves MCP credentials; a dropped secret must never look like success."""

    def _service(self, store: _FakeSecretStore) -> Any:
        service = ExtensionRuntimeService.__new__(ExtensionRuntimeService)
        service.runs = SimpleNamespace(store=store)
        return service

    def _definition(self, **overrides: object) -> McpConnectionDefinition:
        base: dict[str, Any] = {
            "transport": "stdio",
            "command": ["/bin/echo", "hi"],
            "process": {
                "subprocess": True,
                "argv_allowlist": ["/bin/echo"],
                "env_passthrough": ["API_TOKEN"],
                "working_root": "data",
            },
            "credential_ref": "API_TOKEN",
        }
        base.update(overrides)
        return McpConnectionDefinition.from_mapping("conn", base)

    def test_an_allowlisted_stdio_credential_is_passed_through(self) -> None:
        store = _FakeSecretStore()
        store.write_secret("extension:mcp:conn", "API_TOKEN", "s3cret")
        resolved = self._service(store).mcp_credentials(self._definition(), "conn")
        assert resolved == {"API_TOKEN": "s3cret"}

    def test_a_credential_missing_from_env_passthrough_is_refused_not_dropped(self) -> None:
        store = _FakeSecretStore()
        store.write_secret("extension:mcp:conn", "API_TOKEN", "s3cret")
        definition = self._definition(process={
            "subprocess": True,
            "argv_allowlist": ["/bin/echo"],
            "env_passthrough": [],
            "working_root": "data",
        })
        with pytest.raises(ValueError, match="env_passthrough"):
            self._service(store).mcp_credentials(definition, "conn")

    def test_an_oauth_connection_resolves_a_bearer_token(self) -> None:
        store = _FakeSecretStore()
        save_oauth_token(store, "conn", _valid_token())
        definition = McpConnectionDefinition.from_mapping("conn", {
            "transport": "streamable_http",
            "url": "https://mcp.example.test/mcp",
            "oauth": {
                "client_id": "c",
                "authorization_url": "https://auth.example.com/authorize",
                "token_url": "https://auth.example.com/token",
            },
        })
        resolved = self._service(store).mcp_credentials(definition, "conn")
        assert resolved == {"Authorization": "Bearer test-access-token"}


class TestOAuthDefinitionsAreLoadable:
    """An oauth block must survive the definition parser, or the field is unusable."""

    def _manifest(self, oauth: dict[str, Any]) -> Any:
        from backend.app.extensions.discovery import parse_definition_manifest

        document = yaml.safe_dump({
            "id": "conn",
            "name": "Connection",
            "version": "1.0.0",
            "definition": {
                "transport": "streamable_http",
                "url": "https://mcp.example.test/mcp",
                "oauth": oauth,
            },
        })
        return parse_definition_manifest("mcp", document, "s", "data/extensions", "operator")

    def test_endpoint_urls_are_not_treated_as_secrets(self) -> None:
        manifest = self._manifest({
            "client_id": "c",
            "authorization_url": "https://auth.example.test/authorize",
            "token_url": "https://auth.example.test/token",
        })
        assert manifest.definition["oauth"]["token_url"] == "https://auth.example.test/token"
        McpConnectionDefinition.from_mapping("conn", manifest.definition)

    def test_an_inline_client_secret_is_still_refused(self) -> None:
        with pytest.raises(ValueError, match="secret-bearing field"):
            self._manifest({
                "client_id": "c",
                "client_secret": "hunter2",
                "authorization_url": "https://auth.example.test/authorize",
                "token_url": "https://auth.example.test/token",
            })
