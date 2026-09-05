from __future__ import annotations

import base64
import ipaddress
import os
import secrets
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from backend.app.core.paths import DATA_DIR, REPO_ROOT
from backend.app.core.settings import Settings, load_settings
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROFILE_KINDS = {
    "managed_llama_cpp",
    "ollama",
    "openai_compatible",
    "openai",
    "anthropic",
}
LOCAL_PROFILE_KINDS = {"managed_llama_cpp", "ollama", "openai_compatible"}
CLOUD_PROFILE_KINDS = {"openai", "anthropic", "openai_compatible"}
BUILTIN_MANAGED_PROFILE_ID = "builtin:managed-llama-cpp"
LEGACY_OLLAMA_PROFILE_ID = "legacy:ollama"
LEGACY_EXTERNAL_PROFILE_ID = "legacy:external-llama-cpp"
OPENAI_ENDPOINT = "https://api.openai.com/v1"
ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1"
SECRET_KEY_NAME = "JARVIS_SECRET_STORE_KEY"
PREVIOUS_SECRET_KEY_NAME = "JARVIS_SECRET_STORE_PREVIOUS_KEY"
SCHEMA_VERSION = 2


class ProviderConfigError(ValueError):
    pass


class SecretStoreLockedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    profile_id: str
    name: str
    kind: str
    endpoint: str | None
    model: str | None
    context_window: int
    timeout_seconds: float
    has_secret: bool = False
    builtin: bool = False
    updated_at: str | None = None
    secret_updated_at: str | None = None

    @property
    def cloud_eligible(self) -> bool:
        if self.kind in {"openai", "anthropic"}:
            return True
        return self.kind == "openai_compatible" and bool(self.endpoint and self.endpoint.startswith("https://"))

    @property
    def readiness_state(self) -> str:
        if self.kind in {"openai", "anthropic"} and not self.has_secret:
            return "credential_required"
        return "configured"


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    primary_profile_id: str
    local_fallback_profile_id: str | None = None
    cloud_escalation_enabled: bool = False
    cloud_profile_id: str | None = None
    persisted: bool = False


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_endpoint(kind: str, endpoint: str | None) -> str | None:
    if kind == "managed_llama_cpp":
        return None
    if kind == "openai":
        return OPENAI_ENDPOINT
    if kind == "anthropic":
        return ANTHROPIC_ENDPOINT
    raw = (endpoint or "").strip().rstrip("/")
    if not raw:
        raise ProviderConfigError("endpoint is required")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProviderConfigError("endpoint must be an HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderConfigError("endpoint cannot contain credentials, query parameters, or fragments")
    path = parsed.path.rstrip("/")
    if kind == "openai_compatible" and path not in {"", "/v1"}:
        raise ProviderConfigError("OpenAI-compatible endpoint path must be empty or /v1")
    if kind == "ollama" and path:
        raise ProviderConfigError("Ollama endpoint cannot contain a path")
    if parsed.scheme == "http" and not _private_hostname(parsed.hostname):
        raise ProviderConfigError("public provider endpoints require HTTPS")
    normalized_path = "/v1" if kind == "openai_compatible" else ""
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, "", "")).rstrip("/")


def _private_hostname(hostname: str) -> bool:
    lowered = hostname.casefold()
    if (
        lowered == "localhost"
        or lowered.endswith((".localhost", ".local", ".lan", ".internal", ".home"))
        or "." not in lowered
    ):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return bool(address.is_loopback or address.is_private or address.is_link_local)


_BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS operator_schema (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    version INTEGER NOT NULL
);
INSERT OR IGNORE INTO operator_schema(singleton, version) VALUES (1, 1);
CREATE TABLE IF NOT EXISTS llm_provider_profile (
    profile_id TEXT PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    kind TEXT NOT NULL,
    endpoint TEXT,
    model TEXT,
    context_window INTEGER NOT NULL,
    timeout_seconds REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operator_secret (
    owner_id TEXT NOT NULL,
    secret_name TEXT NOT NULL,
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    key_version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(owner_id, secret_name),
    FOREIGN KEY(owner_id) REFERENCES llm_provider_profile(profile_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS llm_provider_selection (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    primary_profile_id TEXT NOT NULL,
    local_fallback_profile_id TEXT,
    cloud_escalation_enabled INTEGER NOT NULL,
    cloud_profile_id TEXT,
    updated_at TEXT NOT NULL
);
"""

_EXTENSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS extension_overlay (
    extension_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('enabled', 'disabled', 'retired')),
    trust TEXT,
    reason TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extension_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    extension_id TEXT NOT NULL,
    prior_state TEXT,
    resulting_state TEXT NOT NULL,
    reason TEXT,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS extension_event_by_extension
    ON extension_event(extension_id, occurred_at);
"""

_MIGRATIONS: dict[int, str] = {1: _EXTENSION_SCHEMA}


class LLMProviderProfileStore:
    def __init__(self, db_path: Path | None = None, env_path: Path | None = None) -> None:
        self.db_path = db_path or DATA_DIR / "operator.sqlite"
        self.env_path = env_path or REPO_ROOT / ".env"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._resume_rotation()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'operator_schema'"
            ).fetchone()
            if existing is not None:
                version = connection.execute("SELECT version FROM operator_schema WHERE singleton = 1").fetchone()
                if version is not None:
                    self._migrate(connection, int(version[0]))
                    return
            connection.executescript(_BASE_SCHEMA + _EXTENSION_SCHEMA)
            connection.execute(
                "UPDATE operator_schema SET version = ? WHERE singleton = 1", (SCHEMA_VERSION,)
            )
            version = connection.execute("SELECT version FROM operator_schema WHERE singleton = 1").fetchone()[0]
            if version != SCHEMA_VERSION:
                raise ProviderConfigError(f"unsupported operator database schema version {version}")

    def _migrate(self, connection: sqlite3.Connection, version: int) -> None:
        if version == SCHEMA_VERSION:
            return
        if version > SCHEMA_VERSION:
            raise ProviderConfigError(f"unsupported operator database schema version {version}")
        # Every step is idempotent DDL, so a crash between the script and the version bump
        # simply re-runs the step on the next open rather than leaving a half-migrated file.
        while version < SCHEMA_VERSION:
            script = _MIGRATIONS.get(version)
            if script is None:
                raise ProviderConfigError(
                    f"no migration path from operator database schema version {version}"
                )
            connection.executescript(script)
            version += 1
            connection.execute(
                "UPDATE operator_schema SET version = ? WHERE singleton = 1", (version,)
            )

    def list_profiles(self, settings: Settings | None = None) -> list[ProviderProfile]:
        profiles = [self.managed_profile()]
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT p.*, EXISTS(
                    SELECT 1 FROM operator_secret s
                    WHERE s.owner_id = p.profile_id AND s.secret_name = 'api_key'
                ) AS has_secret, (
                    SELECT s.updated_at FROM operator_secret s
                    WHERE s.owner_id = p.profile_id AND s.secret_name = 'api_key'
                ) AS secret_updated_at
                FROM llm_provider_profile p ORDER BY p.name COLLATE NOCASE
                """
            ).fetchall()
        profiles.extend(self._profile_from_row(row) for row in rows)
        if not self.selection_persisted():
            legacy = self._legacy_profiles(settings or load_settings())
            saved_ids = {profile.profile_id for profile in profiles}
            profiles.extend(profile for profile in legacy if profile.profile_id not in saved_ids)
        return profiles

    @staticmethod
    def managed_profile() -> ProviderProfile:
        return ProviderProfile(
            profile_id=BUILTIN_MANAGED_PROFILE_ID,
            name="Managed llama.cpp",
            kind="managed_llama_cpp",
            endpoint=None,
            model=None,
            context_window=2048,
            timeout_seconds=30.0,
            builtin=True,
        )

    def get_profile(self, profile_id: str, settings: Settings | None = None) -> ProviderProfile:
        for profile in self.list_profiles(settings):
            if profile.profile_id == profile_id:
                return profile
        raise ProviderConfigError("provider profile not found")

    def create_profile(
        self,
        *,
        name: str,
        kind: str,
        endpoint: str | None,
        model: str | None,
        context_window: int,
        timeout_seconds: float,
        api_key: str | None = None,
    ) -> ProviderProfile:
        profile_id = str(uuid.uuid4())
        self._validate_profile(name, kind, model, context_window, timeout_seconds)
        normalized_endpoint = _normalize_endpoint(kind, endpoint)
        timestamp = _now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO llm_provider_profile(
                        profile_id, name, kind, endpoint, model, context_window,
                        timeout_seconds, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        name.strip(),
                        kind,
                        normalized_endpoint,
                        (model or "").strip() or None,
                        context_window,
                        timeout_seconds,
                        timestamp,
                        timestamp,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ProviderConfigError("provider profile name already exists") from exc
        if api_key:
            self.write_secret(profile_id, "api_key", api_key)
        return self.get_profile(profile_id)

    def update_profile(
        self,
        profile_id: str,
        *,
        name: str,
        kind: str,
        endpoint: str | None,
        model: str | None,
        context_window: int,
        timeout_seconds: float,
        api_key: str | None = None,
        clear_api_key: bool = False,
    ) -> ProviderProfile:
        if profile_id.startswith("builtin:") or profile_id.startswith("legacy:"):
            raise ProviderConfigError("built-in and legacy profiles cannot be edited")
        self._validate_profile(name, kind, model, context_window, timeout_seconds)
        normalized_endpoint = _normalize_endpoint(kind, endpoint)
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE llm_provider_profile SET name = ?, kind = ?, endpoint = ?, model = ?,
                        context_window = ?, timeout_seconds = ?, updated_at = ?
                    WHERE profile_id = ?
                    """,
                    (
                        name.strip(),
                        kind,
                        normalized_endpoint,
                        (model or "").strip() or None,
                        context_window,
                        timeout_seconds,
                        _now(),
                        profile_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ProviderConfigError("provider profile not found")
        except sqlite3.IntegrityError as exc:
            raise ProviderConfigError("provider profile name already exists") from exc
        if clear_api_key:
            self.delete_secret(profile_id, "api_key")
        elif api_key:
            self.write_secret(profile_id, "api_key", api_key)
        return self.get_profile(profile_id)

    def delete_profile(self, profile_id: str) -> None:
        if profile_id.startswith("builtin:") or profile_id.startswith("legacy:"):
            raise ProviderConfigError("built-in and legacy profiles cannot be deleted")
        selection = self.get_selection()
        if profile_id in {
            selection.primary_profile_id,
            selection.local_fallback_profile_id,
            selection.cloud_profile_id,
        }:
            raise ProviderConfigError("selected provider profile cannot be deleted")
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM llm_provider_profile WHERE profile_id = ?", (profile_id,))
            if cursor.rowcount != 1:
                raise ProviderConfigError("provider profile not found")

    def selection_persisted(self) -> bool:
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM llm_provider_selection WHERE singleton = 1").fetchone() is not None

    def get_selection(self, settings: Settings | None = None) -> ProviderSelection:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM llm_provider_selection WHERE singleton = 1").fetchone()
        if row:
            return ProviderSelection(
                primary_profile_id=row["primary_profile_id"],
                local_fallback_profile_id=row["local_fallback_profile_id"],
                cloud_escalation_enabled=bool(row["cloud_escalation_enabled"]),
                cloud_profile_id=row["cloud_profile_id"],
                persisted=True,
            )
        resolved = settings or load_settings()
        external = self._legacy_external_profile(resolved)
        if external:
            primary = external.profile_id
        elif resolved.use_local_model:
            primary = BUILTIN_MANAGED_PROFILE_ID
        elif resolved.use_ollama:
            primary = LEGACY_OLLAMA_PROFILE_ID
        else:
            primary = BUILTIN_MANAGED_PROFILE_ID
        fallback = LEGACY_OLLAMA_PROFILE_ID if resolved.use_ollama and primary != LEGACY_OLLAMA_PROFILE_ID else None
        return ProviderSelection(primary, fallback)

    def set_selection(
        self,
        *,
        primary_profile_id: str,
        local_fallback_profile_id: str | None,
        cloud_escalation_enabled: bool,
        cloud_profile_id: str | None,
        settings: Settings | None = None,
    ) -> ProviderSelection:
        profiles = {profile.profile_id: profile for profile in self.list_profiles(settings)}
        primary = profiles.get(primary_profile_id)
        if primary is None:
            raise ProviderConfigError("primary provider profile not found")
        fallback = profiles.get(local_fallback_profile_id) if local_fallback_profile_id else None
        if local_fallback_profile_id and fallback is None:
            raise ProviderConfigError("local fallback profile not found")
        if fallback and (fallback.kind not in LOCAL_PROFILE_KINDS or fallback.cloud_eligible):
            raise ProviderConfigError("local fallback must use a local provider kind")
        if fallback and fallback.profile_id == primary.profile_id:
            raise ProviderConfigError("local fallback must differ from primary")
        cloud = profiles.get(cloud_profile_id) if cloud_profile_id else None
        if cloud_escalation_enabled and primary.cloud_eligible:
            raise ProviderConfigError("cloud escalation requires a local primary profile")
        if cloud_profile_id and (cloud is None or not cloud.cloud_eligible):
            raise ProviderConfigError("cloud profile must use an eligible cloud provider")
        if cloud_escalation_enabled and cloud is None:
            raise ProviderConfigError("cloud escalation requires an eligible cloud profile")
        if cloud and cloud.profile_id in {primary.profile_id, getattr(fallback, "profile_id", None)}:
            raise ProviderConfigError("cloud profile must differ from primary and local fallback")
        self._persist_selected_legacy_profiles(
            profiles,
            primary_profile_id,
            local_fallback_profile_id,
            cloud_profile_id if cloud_escalation_enabled else None,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO llm_provider_selection(
                    singleton, primary_profile_id, local_fallback_profile_id,
                    cloud_escalation_enabled, cloud_profile_id, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    primary_profile_id = excluded.primary_profile_id,
                    local_fallback_profile_id = excluded.local_fallback_profile_id,
                    cloud_escalation_enabled = excluded.cloud_escalation_enabled,
                    cloud_profile_id = excluded.cloud_profile_id,
                    updated_at = excluded.updated_at
                """,
                (
                    primary_profile_id,
                    local_fallback_profile_id,
                    int(cloud_escalation_enabled),
                    cloud_profile_id,
                    _now(),
                ),
            )
        return self.get_selection(settings)

    def _persist_selected_legacy_profiles(
        self,
        profiles: dict[str, ProviderProfile],
        *profile_ids: str | None,
    ) -> None:
        timestamp = _now()
        with self._connect() as connection:
            for profile_id in profile_ids:
                if not profile_id or not profile_id.startswith("legacy:"):
                    continue
                profile = profiles[profile_id]
                connection.execute(
                    """
                    INSERT OR IGNORE INTO llm_provider_profile(
                        profile_id, name, kind, endpoint, model, context_window,
                        timeout_seconds, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile.profile_id,
                        profile.name,
                        profile.kind,
                        profile.endpoint,
                        profile.model,
                        profile.context_window,
                        profile.timeout_seconds,
                        timestamp,
                        timestamp,
                    ),
                )

    def write_secret(self, owner_id: str, secret_name: str, value: str) -> None:
        if not value:
            raise ProviderConfigError("secret value cannot be empty")
        key = self._master_key(generate=True)
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(key).encrypt(nonce, value.encode("utf-8"), self._aad(owner_id, secret_name))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO operator_secret(owner_id, secret_name, nonce, ciphertext, key_version, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(owner_id, secret_name) DO UPDATE SET
                    nonce = excluded.nonce,
                    ciphertext = excluded.ciphertext,
                    key_version = excluded.key_version,
                    updated_at = excluded.updated_at
                """,
                (owner_id, secret_name, nonce, ciphertext, _now()),
            )

    def read_secret(self, owner_id: str, secret_name: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT nonce, ciphertext FROM operator_secret WHERE owner_id = ? AND secret_name = ?",
                (owner_id, secret_name),
            ).fetchone()
        if row is None:
            return None
        keys = self._available_keys()
        if not keys:
            raise SecretStoreLockedError("secret store key is unavailable")
        for key in keys:
            try:
                plaintext = AESGCM(key).decrypt(row["nonce"], row["ciphertext"], self._aad(owner_id, secret_name))
                return plaintext.decode("utf-8")
            except Exception:
                continue
        raise SecretStoreLockedError("secret store key cannot decrypt stored credentials")

    def delete_secret(self, owner_id: str, secret_name: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM operator_secret WHERE owner_id = ? AND secret_name = ?",
                (owner_id, secret_name),
            )

    def rotate_key(self) -> None:
        file_encoded = self._env_value(SECRET_KEY_NAME)
        current_encoded = os.getenv(SECRET_KEY_NAME) or file_encoded
        if not current_encoded:
            if self._secret_count():
                raise SecretStoreLockedError("secret store key is unavailable")
            self._master_key(generate=True)
            return
        if file_encoded != current_encoded:
            raise SecretStoreLockedError("secret store key is supplied outside .env and cannot be rotated automatically")
        current = self._decode_key(current_encoded)
        replacement = self._encode_key(secrets.token_bytes(32))
        self._write_env_values({SECRET_KEY_NAME: replacement, PREVIOUS_SECRET_KEY_NAME: current_encoded})
        os.environ[SECRET_KEY_NAME] = replacement
        os.environ[PREVIOUS_SECRET_KEY_NAME] = current_encoded
        replacement_key = self._decode_key(replacement)
        with self._connect() as connection:
            rows = connection.execute("SELECT owner_id, secret_name, nonce, ciphertext FROM operator_secret").fetchall()
            for row in rows:
                plaintext = AESGCM(current).decrypt(
                    row["nonce"], row["ciphertext"], self._aad(row["owner_id"], row["secret_name"])
                )
                nonce = secrets.token_bytes(12)
                ciphertext = AESGCM(replacement_key).encrypt(
                    nonce, plaintext, self._aad(row["owner_id"], row["secret_name"])
                )
                connection.execute(
                    "UPDATE operator_secret SET nonce = ?, ciphertext = ?, key_version = key_version + 1, updated_at = ? WHERE owner_id = ? AND secret_name = ?",
                    (nonce, ciphertext, _now(), row["owner_id"], row["secret_name"]),
                )
            self._verify_rows(connection, replacement_key)
        self._write_env_values({PREVIOUS_SECRET_KEY_NAME: None})
        os.environ.pop(PREVIOUS_SECRET_KEY_NAME, None)

    def _resume_rotation(self) -> None:
        file_previous = self._env_value(PREVIOUS_SECRET_KEY_NAME)
        file_current = self._env_value(SECRET_KEY_NAME)
        process_current = os.getenv(SECRET_KEY_NAME)
        previous_encoded = file_previous or os.getenv(PREVIOUS_SECRET_KEY_NAME)
        current_encoded = file_current or process_current
        if not previous_encoded or not current_encoded:
            return
        if file_current and process_current and file_current != process_current:
            raise SecretStoreLockedError(
                "secret store key is supplied outside .env and interrupted rotation cannot resume automatically"
            )
        if not self._secret_count():
            if file_previous:
                self._write_env_values({PREVIOUS_SECRET_KEY_NAME: None})
            os.environ.pop(PREVIOUS_SECRET_KEY_NAME, None)
            return
        current = self._decode_key(current_encoded)
        previous = self._decode_key(previous_encoded)
        with self._connect() as connection:
            rows = connection.execute("SELECT owner_id, secret_name, nonce, ciphertext FROM operator_secret").fetchall()
            pending: list[tuple[bytes, bytes, str, str]] = []
            for row in rows:
                aad = self._aad(row["owner_id"], row["secret_name"])
                try:
                    AESGCM(current).decrypt(row["nonce"], row["ciphertext"], aad)
                    continue
                except Exception:
                    plaintext = AESGCM(previous).decrypt(row["nonce"], row["ciphertext"], aad)
                    nonce = secrets.token_bytes(12)
                    ciphertext = AESGCM(current).encrypt(nonce, plaintext, aad)
                    pending.append((nonce, ciphertext, row["owner_id"], row["secret_name"]))
            for nonce, ciphertext, owner_id, secret_name in pending:
                connection.execute(
                    "UPDATE operator_secret SET nonce = ?, ciphertext = ?, key_version = key_version + 1, updated_at = ? WHERE owner_id = ? AND secret_name = ?",
                    (nonce, ciphertext, _now(), owner_id, secret_name),
                )
            self._verify_rows(connection, current)
        if self._env_value(PREVIOUS_SECRET_KEY_NAME):
            self._write_env_values({PREVIOUS_SECRET_KEY_NAME: None})
        os.environ.pop(PREVIOUS_SECRET_KEY_NAME, None)

    def _master_key(self, *, generate: bool) -> bytes:
        encoded = os.getenv(SECRET_KEY_NAME) or self._env_value(SECRET_KEY_NAME)
        if encoded:
            return self._decode_key(encoded)
        if self._secret_count():
            raise SecretStoreLockedError("secret store key is unavailable")
        if not generate:
            raise SecretStoreLockedError("secret store key is unavailable")
        encoded = self._encode_key(secrets.token_bytes(32))
        self._write_env_values({SECRET_KEY_NAME: encoded})
        os.environ[SECRET_KEY_NAME] = encoded
        return self._decode_key(encoded)

    def _available_keys(self) -> list[bytes]:
        values = [
            os.getenv(SECRET_KEY_NAME) or self._env_value(SECRET_KEY_NAME),
            os.getenv(PREVIOUS_SECRET_KEY_NAME) or self._env_value(PREVIOUS_SECRET_KEY_NAME),
        ]
        return [self._decode_key(value) for value in values if value]

    @staticmethod
    def _encode_key(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii")

    @staticmethod
    def _decode_key(value: str) -> bytes:
        try:
            decoded = base64.urlsafe_b64decode(value.encode("ascii"))
        except Exception as exc:
            raise SecretStoreLockedError("secret store key is invalid") from exc
        if len(decoded) != 32:
            raise SecretStoreLockedError("secret store key must decode to 32 bytes")
        return decoded

    @staticmethod
    def _aad(owner_id: str, secret_name: str) -> bytes:
        return f"jarvisv7:{SCHEMA_VERSION}:{owner_id}:{secret_name}".encode()

    def _secret_count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM operator_secret").fetchone()[0])

    def _verify_rows(self, connection: sqlite3.Connection, key: bytes) -> None:
        rows = connection.execute(
            "SELECT owner_id, secret_name, nonce, ciphertext FROM operator_secret"
        ).fetchall()
        for row in rows:
            AESGCM(key).decrypt(
                row["nonce"],
                row["ciphertext"],
                self._aad(row["owner_id"], row["secret_name"]),
            )

    def _env_value(self, name: str) -> str | None:
        if not self.env_path.is_file():
            return None
        for line in self.env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip() or None
        return None

    def _write_env_values(self, updates: dict[str, str | None]) -> None:
        if not self.env_path.is_file():
            raise SecretStoreLockedError(".env is required before credentials can be stored")
        lines = self.env_path.read_text(encoding="utf-8").splitlines(keepends=True)
        remaining = dict(updates)
        rendered: list[str] = []
        for line in lines:
            if "=" not in line or line.lstrip().startswith("#"):
                rendered.append(line)
                continue
            key = line.split("=", 1)[0].strip()
            if key not in remaining:
                rendered.append(line)
                continue
            value = remaining.pop(key)
            if value is not None:
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                rendered.append(f"{key}={value}{newline}")
        for key, value in remaining.items():
            if value is not None:
                if rendered and not rendered[-1].endswith(("\n", "\r")):
                    rendered[-1] += "\n"
                rendered.append(f"{key}={value}\n")
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".env.", dir=self.env_path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.writelines(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.env_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _validate_profile(name: str, kind: str, model: str | None, context_window: int, timeout_seconds: float) -> None:
        if kind not in PROFILE_KINDS or kind == "managed_llama_cpp":
            raise ProviderConfigError("unsupported editable provider kind")
        if not name.strip() or len(name.strip()) > 80:
            raise ProviderConfigError("profile name must contain 1 to 80 characters")
        if not (model or "").strip():
            raise ProviderConfigError("model is required")
        if not 512 <= context_window <= 2_000_000:
            raise ProviderConfigError("context window must be between 512 and 2000000")
        if not 1.0 <= timeout_seconds <= 600.0:
            raise ProviderConfigError("timeout must be between 1 and 600 seconds")

    @staticmethod
    def _profile_from_row(row: sqlite3.Row) -> ProviderProfile:
        return ProviderProfile(
            profile_id=row["profile_id"],
            name=row["name"],
            kind=row["kind"],
            endpoint=row["endpoint"],
            model=row["model"],
            context_window=int(row["context_window"]),
            timeout_seconds=float(row["timeout_seconds"]),
            has_secret=bool(row["has_secret"]),
            updated_at=row["updated_at"],
            secret_updated_at=row["secret_updated_at"],
        )

    def _legacy_profiles(self, settings: Settings) -> list[ProviderProfile]:
        profiles: list[ProviderProfile] = []
        external = self._legacy_external_profile(settings)
        if external:
            profiles.append(external)
        if settings.use_ollama:
            profiles.append(
                ProviderProfile(
                    profile_id=LEGACY_OLLAMA_PROFILE_ID,
                    name="Ollama (.env)",
                    kind="ollama",
                    endpoint=_normalize_endpoint("ollama", settings.ollama_base_url),
                    model=settings.ollama_model,
                    context_window=settings.ollama_num_ctx or 2048,
                    timeout_seconds=60.0,
                    builtin=True,
                )
            )
        return profiles

    @staticmethod
    def _legacy_external_profile(settings: Settings) -> ProviderProfile | None:
        if not (
            settings.llama_cpp_managed_explicit
            and not settings.llama_cpp_managed
            and settings.llama_cpp_base_url_explicit
            and settings.llama_cpp_base_url.strip()
        ):
            return None
        return ProviderProfile(
            profile_id=LEGACY_EXTERNAL_PROFILE_ID,
            name="External llama.cpp (.env)",
            kind="openai_compatible",
            endpoint=_normalize_endpoint("openai_compatible", settings.llama_cpp_base_url),
            model=settings.llama_cpp_model_name or "local-llama-cpp",
            context_window=settings.llama_cpp_context_size,
            timeout_seconds=settings.llama_cpp_timeout_seconds,
            builtin=True,
        )
