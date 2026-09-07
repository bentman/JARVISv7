"""OAuth 2.0 authorization code flow for MCP server credentials."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import stat
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class McpOAuthConfig:
    authorization_url: str
    token_url: str
    client_id: str
    client_secret: str = ""
    scopes: tuple[str, ...] = ()
    redirect_port: int = 19823
    pkce: bool = True

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
        if self._config.pkce:
            code_verifier = secrets.token_urlsafe(64)
            digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
            code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
            # Append verifier to state so we can retrieve it later
            state = f"{state}:{code_verifier}"
        url = f"{self._config.authorization_url}?{urllib.parse.urlencode(params)}"
        return url, state

    def exchange_code(
        self, code: str, state: str, code_verifier: str | None = None
    ) -> McpOAuthToken:
        body: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"http://127.0.0.1:{self._config.redirect_port}/callback",
            "client_id": self._config.client_id,
        }
        if self._config.client_secret:
            body["client_secret"] = self._config.client_secret
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
        data = self._post_token(body)
        return self._parse_token(data)

    def _run_local_callback(self, port: int, timeout: int = 300) -> str:
        result: dict[str, str] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
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
        return result["code"]

    def _post_token(self, body: dict[str, str]) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(body).encode("utf-8")
        req = urllib.request.Request(
            self._config.token_url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
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


class McpOAuthTokenStore:
    def __init__(self, store_path: Path) -> None:
        self._store_path = store_path / "mcp_oauth"

    def save(self, connection_id: str, token: McpOAuthToken) -> str:
        self._store_path.mkdir(parents=True, exist_ok=True)
        filename = f"{connection_id}.json"
        filepath = self._store_path / filename
        filepath.write_text(json.dumps(token.to_dict()), encoding="utf-8")
        os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        return f"oauth:{connection_id}"

    def load(self, credential_ref: str) -> McpOAuthToken | None:
        if not credential_ref.startswith("oauth:"):
            return None
        connection_id = credential_ref[len("oauth:"):]
        filepath = self._store_path / f"{connection_id}.json"
        if not filepath.is_file():
            return None
        data = json.loads(filepath.read_text(encoding="utf-8"))
        return McpOAuthToken(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            refresh_token=data.get("refresh_token"),
            expires_at=data.get("expires_at"),
            scope=data.get("scope", ""),
        )

    def delete(self, credential_ref: str) -> None:
        if not credential_ref.startswith("oauth:"):
            return
        connection_id = credential_ref[len("oauth:"):]
        filepath = self._store_path / f"{connection_id}.json"
        if filepath.is_file():
            filepath.unlink()
