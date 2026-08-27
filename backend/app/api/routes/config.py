from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.api.schemas.config import (
    OperatorConfigField,
    OperatorConfigRejectedField,
    OperatorConfigResponse,
    OperatorConfigWriteRequest,
    OperatorConfigWriteResponse,
)
from backend.app.core.paths import REPO_ROOT
from fastapi import APIRouter, HTTPException

router = APIRouter()

ENV_FILE = REPO_ROOT / ".env"


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

_OPERATOR_FIELDS = {spec.key: spec for spec in OPERATOR_FIELD_SPECS}


def _require_env_file(path: Path | None = None) -> None:
    env_file = path or ENV_FILE
    if not env_file.is_file():
        raise HTTPException(status_code=409, detail={"error": "env_file_missing"})


def _parse_env_values(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.rstrip("\r\n")
    return values


def _render_field(spec: OperatorFieldSpec, values: dict[str, str]) -> OperatorConfigField:
    raw_value = values.get(spec.key, "")
    has_value = raw_value != ""
    value = "***" if spec.secret and has_value else "" if spec.secret else raw_value
    return OperatorConfigField(
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


@router.get("/config/operator", response_model=OperatorConfigResponse)
def get_operator_config() -> OperatorConfigResponse:
    _require_env_file()
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    values = _parse_env_values(lines)
    return OperatorConfigResponse(fields=[_render_field(spec, values) for spec in OPERATOR_FIELD_SPECS])


@router.post("/config/operator", response_model=OperatorConfigWriteResponse)
def write_operator_config(request: OperatorConfigWriteRequest) -> OperatorConfigWriteResponse:
    _require_env_file()
    written: list[str] = []
    rejected: list[OperatorConfigRejectedField] = []
    accepted: dict[str, str] = {}
    for key, value in request.fields.items():
        spec = _OPERATOR_FIELDS.get(key)
        if spec is None:
            rejected.append(OperatorConfigRejectedField(key=key, reason="not_allowlisted"))
            continue
        if "\r" in value or "\n" in value:
            rejected.append(OperatorConfigRejectedField(key=key, reason="value_contains_line_break"))
            continue
        if spec.secret and value == "***":
            continue
        accepted[key] = value

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
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
        ENV_FILE.write_text("".join(rewritten), encoding="utf-8")
    return OperatorConfigWriteResponse(written=written, rejected=rejected)
