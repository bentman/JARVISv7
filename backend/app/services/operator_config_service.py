from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.app.core.paths import REPO_ROOT


@dataclass(frozen=True, slots=True)
class OperatorFieldSpec:
    key: str
    description: str
    secret: bool = False
    editable: bool = True
    restart_required: bool = True
    options: tuple[str, ...] | None = None
    section: str | None = None
    advanced: bool = False


OPERATOR_FIELD_SPECS: tuple[OperatorFieldSpec, ...] = (
    OperatorFieldSpec("JARVIS_LANGUAGE", "Primary assistant language.", section="App Defaults"),
    OperatorFieldSpec("USE_SEARXNG", "Enable SearXNG search escalation.", section="Optional Services"),
    OperatorFieldSpec("USE_DDGS", "Enable DDGS search fallback.", section="Optional Services"),
    OperatorFieldSpec("USE_TAVILY", "Enable Tavily search fallback.", section="Optional Services"),
    OperatorFieldSpec("SEARXNG_PORT", "SearXNG service port.", section="Optional Services"),
    OperatorFieldSpec("SEARXNG_BASE_URL", "SearXNG endpoint URL.", section="Optional Services", advanced=True),
    OperatorFieldSpec("TAVILY_API_KEY", "Tavily API key.", secret=True, section="Optional Services", advanced=True),
    OperatorFieldSpec("REDIS_HOST", "Redis host.", section="Optional Services"),
    OperatorFieldSpec("REDIS_PORT", "Redis port.", section="Optional Services"),
    OperatorFieldSpec("REDIS_DB", "Redis database number.", section="Optional Services", advanced=True),
    OperatorFieldSpec("REDIS_MAX_CONNECTIONS", "Redis maximum connection count.", section="Optional Services", advanced=True),
    OperatorFieldSpec("REDIS_SOCKET_TIMEOUT", "Redis socket timeout in seconds.", section="Optional Services", advanced=True),
)

ENV_FILE = REPO_ROOT / ".env"
SECRET_SENTINEL = "***"


@dataclass(frozen=True, slots=True)
class OperatorConfigError(Exception):
    status_code: int
    error: str
    message: str

    def detail(self) -> dict[str, str]:
        return {"error": self.error, "message": self.message}


@dataclass(frozen=True, slots=True)
class OperatorConfigFieldView:
    key: str
    value: str
    has_value: bool
    editable: bool
    secret: bool
    restart_required: bool
    description: str
    options: list[str] | None = None
    section: str | None = None
    advanced: bool = False


@dataclass(frozen=True, slots=True)
class OperatorConfigView:
    fields: list[OperatorConfigFieldView] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class OperatorConfigRejectedFieldView:
    key: str
    reason: str


@dataclass(frozen=True, slots=True)
class OperatorConfigWriteView:
    written: list[str] = field(default_factory=list)
    rejected: list[OperatorConfigRejectedFieldView] = field(default_factory=list)


class OperatorConfigService:
    def __init__(self, specs: tuple[OperatorFieldSpec, ...] = OPERATOR_FIELD_SPECS) -> None:
        self.specs = specs

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self.specs)

    def read(self, *, env_file: Path) -> OperatorConfigView:
        values = self._values(env_file)
        return OperatorConfigView(fields=[self._render(spec, values) for spec in self.specs])

    def write(self, fields: dict[str, str], *, env_file: Path) -> OperatorConfigWriteView:
        index = {spec.key: spec for spec in self.specs}
        written: list[str] = []
        rejected: list[OperatorConfigRejectedFieldView] = []
        accepted: dict[str, str] = {}
        for key, value in fields.items():
            spec = index.get(key)
            if spec is None:
                rejected.append(OperatorConfigRejectedFieldView(key=key, reason="not_allowlisted"))
                continue
            if "\r" in value or "\n" in value:
                rejected.append(
                    OperatorConfigRejectedFieldView(key=key, reason="value_contains_line_break")
                )
                continue
            if spec.secret and value == SECRET_SENTINEL:
                continue
            accepted[key] = value

        lines = self._lines(env_file)
        remaining = dict(accepted)
        rewritten: list[str] = []
        for line in lines:
            if "=" not in line or line.lstrip().startswith("#"):
                rewritten.append(line)
                continue
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                rewritten.append(_replace_env_line(line, remaining.pop(key)))
                written.append(key)
                continue
            rewritten.append(line)

        if remaining:
            if rewritten and not rewritten[-1].endswith(("\n", "\r\n")):
                rewritten[-1] = f"{rewritten[-1]}\n"
            for key, value in remaining.items():
                rewritten.append(f"{key}={value}\n")
                written.append(key)

        if written:
            env_file.write_text("".join(rewritten), encoding="utf-8")
        return OperatorConfigWriteView(written=written, rejected=rejected)

    def _lines(self, env_file: Path) -> list[str]:
        if not env_file.is_file():
            raise OperatorConfigError(409, "env_file_missing", "the .env file is missing")
        return env_file.read_text(encoding="utf-8").splitlines(keepends=True)

    def _values(self, env_file: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in self._lines(env_file):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.rstrip("\r\n")
        return values

    def _render(self, spec: OperatorFieldSpec, values: dict[str, str]) -> OperatorConfigFieldView:
        raw_value = values.get(spec.key, "")
        has_value = raw_value != ""
        value = SECRET_SENTINEL if spec.secret and has_value else "" if spec.secret else raw_value
        return OperatorConfigFieldView(
            key=spec.key,
            value=value,
            has_value=has_value,
            editable=spec.editable,
            secret=spec.secret,
            restart_required=spec.restart_required,
            description=spec.description,
            options=list(spec.options) if spec.options else None,
            section=spec.section,
            advanced=spec.advanced,
        )


def _replace_env_line(line: str, value: str) -> str:
    key, _old_value = line.split("=", 1)
    newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    return f"{key}={value}{newline}"
