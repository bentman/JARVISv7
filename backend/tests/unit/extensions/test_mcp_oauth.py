"""Tests for MCP OAuth credential management."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from backend.app.extensions.mcp import McpConnectionDefinition
from backend.app.extensions.mcp_oauth import (
    McpOAuthConfig,
    McpOAuthFlow,
    McpOAuthToken,
    McpOAuthTokenStore,
)


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
        # State includes code_verifier separated by colon
        assert ":" in state

    def test_start_authorization_without_pkce(self) -> None:
        config = _valid_oauth_config(pkce=False)
        flow = McpOAuthFlow(config)
        url, state = flow.start_authorization()
        assert "code_challenge=" not in url
        assert ":" not in state

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
        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            token = flow.exchange_code("auth-code", "state123", code_verifier="verifier")
            assert token.access_token == "new-token"
            assert token.refresh_token == "new-refresh"
            call_args = mock_urlopen.call_args[0][0]
            assert call_args.get_method() == "POST"
            body = call_args.data.decode("utf-8")
            assert "grant_type=authorization_code" in body
            assert "code=auth-code" in body
            assert "code_verifier=verifier" in body

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


class TestMcpOAuthTokenStore:
    def test_save_load_delete_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = McpOAuthTokenStore(Path(tmpdir))
            token = _valid_token()
            ref = store.save("test-conn", token)
            assert ref == "oauth:test-conn"
            loaded = store.load(ref)
            assert loaded is not None
            assert loaded.access_token == token.access_token
            assert loaded.refresh_token == token.refresh_token
            store.delete(ref)
            assert store.load(ref) is None

    @pytest.mark.skipif(os.name == "nt", reason="validates Linux/POSIX file-permission-mode semantics")
    def test_file_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = McpOAuthTokenStore(Path(tmpdir))
            token = _valid_token()
            store.save("test-conn", token)
            filepath = Path(tmpdir) / "mcp_oauth" / "test-conn.json"
            mode = os.stat(filepath).st_mode
            assert stat.S_IMODE(mode) == 0o600

    def test_load_non_oauth_ref_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = McpOAuthTokenStore(Path(tmpdir))
            assert store.load("bearer:some-token") is None

    def test_load_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = McpOAuthTokenStore(Path(tmpdir))
            assert store.load("oauth:nonexistent") is None

    def test_delete_non_oauth_ref_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = McpOAuthTokenStore(Path(tmpdir))
            store.delete("bearer:some-token")  # should not raise


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
        with pytest.raises(ValueError, match="oauth.authorization_url must be a valid HTTPS URL"):
            McpConnectionDefinition.from_mapping("test", self._valid_mapping(oauth=oauth))

    def test_oauth_empty_client_id(self) -> None:
        oauth = {
            "authorization_url": "https://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            "client_id": "",
        }
        with pytest.raises(ValueError, match="oauth.client_id must be a non-empty string"):
            McpConnectionDefinition.from_mapping("test", self._valid_mapping(oauth=oauth))

    def test_oauth_invalid_scopes(self) -> None:
        oauth = {
            "authorization_url": "https://auth.example.com/authorize",
            "token_url": "https://auth.example.com/token",
            "client_id": "my-client",
            "scopes": [""],
        }
        with pytest.raises(ValueError, match="oauth.scopes must be a list of non-empty strings"):
            McpConnectionDefinition.from_mapping("test", self._valid_mapping(oauth=oauth))

    def test_oauth_none_is_valid(self) -> None:
        defn = McpConnectionDefinition.from_mapping("test", self._valid_mapping())
        assert defn.oauth is None

    def test_oauth_not_mapping_raises(self) -> None:
        with pytest.raises(ValueError, match="oauth must be a mapping"):
            McpConnectionDefinition.from_mapping("test", self._valid_mapping(oauth="not-a-dict"))
