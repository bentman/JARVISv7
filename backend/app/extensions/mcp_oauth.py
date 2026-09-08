"""OAuth 2.0 authorization code flow for MCP server credentials."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlsplit

# A token endpoint that never answers must not hold the flow open indefinitely.
_TOKEN_REQUEST_TIMEOUT_S = 30


@dataclass(frozen=True, slots=True)
class McpOAuthConfig:
    authorization_url: str
    token_url: str
    client_id: str
    client_secret: str = ""
    scopes: tuple[str, ...] = ()
    redirect_port: int = 19823
    pkce: bool = True
    # RFC 8707: binds the issued token to one MCP server so it cannot be replayed
    # against a different resource.
    resource: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("authorization_url", "token_url"):
            value = getattr(self, field_name)
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError(f"{field_name} must be a valid HTTPS URL")
        if not self.client_id:
            raise ValueError("client_id must be non-empty")
        if any(not scope or not isinstance(scope, str) for scope in self.scopes):
            raise ValueError("scopes entries must be non-empty strings")
        if not isinstance(self.redirect_port, int) or not (1024 <= self.redirect_port <= 65535):
            raise ValueError("redirect_port must be between 1024 and 65535")
        if self.resource is not None:
            parsed = urlsplit(self.resource)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("resource must be a valid HTTP(S) URL")


@dataclass(frozen=True, slots=True)
class McpOAuthToken:
    access_token: str
    token_type: str = "Bearer"
    refresh_token: str | None = None
    expires_at: str | None = None
    scope: str = ""

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            return datetime.now(UTC) >= exp
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class McpOAuthFlow:
    def __init__(self, config: McpOAuthConfig) -> None:
        self._config = config
        # The PKCE verifier must never leave the host: it is held against the state it
        # was minted with and consumed once, so a replayed or unknown state cannot
        # redeem an authorization code.
        self._pending: dict[str, str | None] = {}

    def start_authorization(self) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self._config.client_id,
            "state": state,
            "redirect_uri": f"http://127.0.0.1:{self._config.redirect_port}/callback",
        }
        if self._config.scopes:
            params["scope"] = " ".join(self._config.scopes)
        if self._config.resource:
            params["resource"] = self._config.resource
        code_verifier: str | None = None
        if self._config.pkce:
            code_verifier = secrets.token_urlsafe(64)
            digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
            code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        self._pending[state] = code_verifier
        url = f"{self._config.authorization_url}?{urllib.parse.urlencode(params)}"
        return url, state

    def exchange_code(self, code: str, state: str) -> McpOAuthToken:
        if state not in self._pending:
            raise ValueError("authorization state is unknown or already used")
        code_verifier = self._pending.pop(state)
        body: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"http://127.0.0.1:{self._config.redirect_port}/callback",
            "client_id": self._config.client_id,
        }
        if self._config.client_secret:
            body["client_secret"] = self._config.client_secret
        if self._config.resource:
            body["resource"] = self._config.resource
        if code_verifier:
            body["code_verifier"] = code_verifier
        data = self._post_token(body)
        return self._parse_token(data)

    def refresh_token(self, token: McpOAuthToken) -> McpOAuthToken:
        if not token.refresh_token:
            raise ValueError("token has no refresh_token")
        body: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": self._config.client_id,
        }
        if self._config.client_secret:
            body["client_secret"] = self._config.client_secret
        if self._config.resource:
            body["resource"] = self._config.resource
        data = self._post_token(body)
        return self._parse_token(data)

    def _run_local_callback(self, port: int, timeout: int = 300) -> tuple[str, str]:
        result: dict[str, str] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                code = params.get("code", [""])[0]
                state = params.get("state", [""])[0]
                if code:
                    result["code"] = code
                    result["state"] = state
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        b"<html><body><h1>Authorization successful</h1>"
                        b"<p>You can close this window.</p></body></html>"
                    )
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing authorization code")

            def log_message(self, format: str, *args: Any) -> None:
                pass  # suppress server logs

        server = HTTPServer(("127.0.0.1", port), Handler)
        server.timeout = timeout
        server.handle_request()
        server.server_close()
        if "code" not in result:
            raise TimeoutError("OAuth callback not received within timeout")
        return result["code"], result.get("state", "")

    def _post_token(self, body: dict[str, str]) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(body).encode("utf-8")
        req = urllib.request.Request(
            self._config.token_url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TOKEN_REQUEST_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _parse_token(data: dict[str, Any]) -> McpOAuthToken:
        from datetime import timedelta

        expires_in = data.get("expires_in")
        expires_at: str | None = None
        if isinstance(expires_in, (int, float)):
            expires_at = (
                datetime.now(UTC) + timedelta(seconds=int(expires_in))
            ).isoformat()
        return McpOAuthToken(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scope=data.get("scope", ""),
        )


def parse_resource_metadata_url(www_authenticate: str) -> str | None:
    """Read the resource_metadata hint from a 401 challenge (RFC 9728 section 5.1)."""
    for part in www_authenticate.split(","):
        key, _, value = part.strip().partition("=")
        if key.strip().lower().endswith("resource_metadata"):
            return value.strip().strip('"') or None
    return None


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(request, timeout=_TOKEN_REQUEST_TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


def protected_resource_metadata_url(resource_url: str) -> str:
    """Build the RFC 9728 well-known URL, preserving the resource path."""
    parsed = urlsplit(resource_url)
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource{path}"


def discover_authorization_server(resource_url: str) -> dict[str, Any]:
    """Discover the authorization server for an MCP resource.

    Follows RFC 9728 protected-resource metadata to an issuer, then RFC 8414
    authorization-server metadata for its endpoints, so an operator does not have to
    hand-configure endpoints that the server already advertises.
    """
    metadata = _fetch_json(protected_resource_metadata_url(resource_url))
    issuers = metadata.get("authorization_servers") or []
    if not issuers:
        raise ValueError("protected-resource metadata declares no authorization server")
    issuer = str(issuers[0]).rstrip("/")
    server = _fetch_json(f"{issuer}/.well-known/oauth-authorization-server")
    for required in ("authorization_endpoint", "token_endpoint"):
        if not isinstance(server.get(required), str) or not server[required]:
            raise ValueError(f"authorization-server metadata is missing {required}")
    return {
        "authorization_url": server["authorization_endpoint"],
        "token_url": server["token_endpoint"],
        "scopes_supported": tuple(metadata.get("scopes_supported", ()) or ()),
        "resource": metadata.get("resource", resource_url),
        "issuer": issuer,
    }


OAUTH_SECRET_NAME = "oauth_token"


def oauth_owner_id(connection_id: str) -> str:
    return f"extension:mcp:{connection_id}"


def save_oauth_token(store: Any, connection_id: str, token: McpOAuthToken) -> None:
    """Persist an OAuth token in the application's encrypted secret store."""
    store.write_secret(oauth_owner_id(connection_id), OAUTH_SECRET_NAME, json.dumps(token.to_dict()))


def load_oauth_token(store: Any, connection_id: str) -> McpOAuthToken | None:
    raw = store.read_secret(oauth_owner_id(connection_id), OAUTH_SECRET_NAME)
    if not raw:
        return None
    data = json.loads(raw)
    return McpOAuthToken(
        access_token=data["access_token"],
        token_type=data.get("token_type", "Bearer"),
        refresh_token=data.get("refresh_token"),
        expires_at=data.get("expires_at"),
        scope=data.get("scope", ""),
    )


def config_from_definition(
    oauth: dict[str, Any], *, resource_url: str | None = None
) -> McpOAuthConfig:
    """Build a flow config, discovering endpoints when the definition omits them."""
    authorization_url = oauth.get("authorization_url")
    token_url = oauth.get("token_url")
    scopes = tuple(oauth.get("scopes", ()))
    resource = oauth.get("resource") or resource_url
    if not authorization_url or not token_url:
        if not resource_url:
            raise ValueError("oauth endpoints are undiscoverable without a connection url")
        discovered = discover_authorization_server(resource_url)
        authorization_url = authorization_url or discovered["authorization_url"]
        token_url = token_url or discovered["token_url"]
        scopes = scopes or discovered["scopes_supported"]
        resource = resource or discovered["resource"]
    return McpOAuthConfig(
        authorization_url=authorization_url,
        token_url=token_url,
        client_id=oauth["client_id"],
        client_secret=oauth.get("client_secret", ""),
        scopes=scopes,
        redirect_port=oauth.get("redirect_port", 19823),
        resource=resource,
    )


def resolve_oauth_bearer(
    store: Any, connection_id: str, oauth: dict[str, Any], *, resource_url: str | None = None
) -> str:
    """Return a usable access token, refreshing it when it has expired.

    A refreshed token is written back so the next connection does not re-refresh.
    """
    token = load_oauth_token(store, connection_id)
    if token is None:
        raise ValueError("MCP connection is not authorized; complete its OAuth connection first")
    if token.is_expired():
        if not token.refresh_token:
            raise ValueError("MCP authorization expired; reconnect this MCP connection")
        config = config_from_definition(oauth, resource_url=resource_url)
        token = McpOAuthFlow(config).refresh_token(token)
        save_oauth_token(store, connection_id, token)
    return token.access_token
