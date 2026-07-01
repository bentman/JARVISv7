from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.core.paths import CONFIG_DIR, DATA_DIR, MODELS_DIR, REPO_ROOT

ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE_FILE = REPO_ROOT / ".env.example"

SETTING_ENV_CLASSIFICATION: dict[str, str] = {
    "APP_NAME": "primary",
    "JARVIS_LANGUAGE": "primary",
    "CONFIG_PATH": "advanced",
    "DATA_PATH": "advanced",
    "MODEL_PATH": "advanced",
    "TOOL_FILESYSTEM_SANDBOX_PATH": "advanced",
    "USE_LOCAL_MODEL": "primary",
    "LLM_MODEL_POLICY": "primary",
    "LLM_MODEL_ID": "advanced",
    "LOCAL_MODEL_FETCH": "derived",
    "LLAMA_CPP_MANAGED": "derived",
    "LLAMA_CPP_MODEL_PATH": "advanced",
    "LLAMA_CPP_BASE_URL": "advanced",
    "LLAMA_CPP_HOST": "advanced",
    "LLAMA_CPP_PORT": "advanced",
    "LLAMA_CPP_BINARY_PATH": "advanced",
    "LLAMA_CPP_MODEL_NAME": "advanced",
    "LLAMA_CPP_TIMEOUT_SECONDS": "advanced",
    "USE_OLLAMA": "primary",
    "OLLAMA_BASE_URL": "advanced",
    "JARVISV7_OLLAMA_URL": "compatibility",
    "OLLAMA_MODEL": "primary",
    "OLLAMA_NUM_CTX": "advanced",
    "JARVISV7_LIVE_TESTS": "test-only",
    "TTS_MODELS": "advanced",
    "STT_MODELS": "advanced",
    "WAKE_MODEL": "advanced",
    "RESIDENT_VOICE_SPEECH_RMS_THRESHOLD": "advanced",
    "RESIDENT_VOICE_NO_SPEECH_TIMEOUT_SECONDS": "advanced",
    "RESIDENT_VOICE_SILENCE_END_SECONDS": "advanced",
    "RESIDENT_VOICE_MAX_DURATION_SECONDS": "advanced",
    "RESIDENT_VOICE_PRE_ROLL_SECONDS": "advanced",
    "RESIDENT_VOICE_MIN_SPEECH_SECONDS": "advanced",
    "QAIRT_SDK_PATH": "advanced",
    "PICOVOICE_ACCESS_KEY": "secret",
    "PVPORCUPINE_MODEL_PATH": "advanced",
    "REDIS_HOST": "services",
    "REDIS_PORT": "services",
    "REDIS_DB": "advanced",
    "REDIS_MAX_CONNECTIONS": "advanced",
    "REDIS_SOCKET_TIMEOUT": "advanced",
    "USE_SEARXNG": "primary",
    "SEARXNG_PORT": "services",
    "SEARXNG_BASE_URL": "derived",
    "USE_DDGS": "primary",
    "USE_TAVILY": "primary",
    "TAVILY_API_KEY": "secret",
}


def _load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=False)
        return
    if ENV_EXAMPLE_FILE.exists():
        load_dotenv(ENV_EXAMPLE_FILE, override=False)


_load_dotenv_if_present()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    if not stripped:
        return default
    return stripped.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return int(value)


def _env_float(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return float(value)


def _env_present(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.strip() != ""


def _env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value


def _env_path(name: str, default: Path | str) -> Path:
    value = _env_str(name)
    return Path(value) if value is not None else Path(default)


def _endpoint_url_from_host_port(host: str, port: int) -> str:
    return f"http://{host}:{port}"


@dataclass(slots=True)
class Settings:
    app_name: str = field(default_factory=lambda: _env_str("APP_NAME", "JARVISv7") or "JARVISv7")
    jarvis_language: str = field(default_factory=lambda: _env_str("JARVIS_LANGUAGE", "english") or "english")
    config_path: Path = field(
        default_factory=lambda: _env_path("CONFIG_PATH", CONFIG_DIR)
    )
    data_path: Path = field(default_factory=lambda: _env_path("DATA_PATH", DATA_DIR))
    tool_filesystem_sandbox_path: Path = field(
        default_factory=lambda: _env_path("TOOL_FILESYSTEM_SANDBOX_PATH", "data/tool_sandbox/")
    )
    model_path: Path = field(default_factory=lambda: _env_path("MODEL_PATH", MODELS_DIR))
    use_local_model: bool = field(default_factory=lambda: _env_bool("USE_LOCAL_MODEL", True))
    local_model_fetch_explicit: bool = field(default_factory=lambda: _env_present("LOCAL_MODEL_FETCH"))
    local_model_fetch: bool = field(default_factory=lambda: _env_bool("LOCAL_MODEL_FETCH", False))
    llm_model_policy: str | None = field(default_factory=lambda: _env_str("LLM_MODEL_POLICY", "auto"))
    llm_model_id: str | None = field(default_factory=lambda: _env_str("LLM_MODEL_ID"))
    llama_cpp_model_path: str | None = field(
        default_factory=lambda: _env_str("LLAMA_CPP_MODEL_PATH")
    )
    llama_cpp_base_url: str = field(
        default_factory=lambda: _env_str("LLAMA_CPP_BASE_URL")
        or _endpoint_url_from_host_port(_env_str("LLAMA_CPP_HOST", "127.0.0.1") or "127.0.0.1", _env_int("LLAMA_CPP_PORT") or 8080)
    )
    llama_cpp_host: str = field(default_factory=lambda: _env_str("LLAMA_CPP_HOST", "127.0.0.1") or "127.0.0.1")
    llama_cpp_port: int = field(default_factory=lambda: _env_int("LLAMA_CPP_PORT") or 8080)
    llama_cpp_binary_path: str | None = field(
        default_factory=lambda: _env_str("LLAMA_CPP_BINARY_PATH")
    )
    llama_cpp_managed_explicit: bool = field(default_factory=lambda: _env_present("LLAMA_CPP_MANAGED"))
    llama_cpp_managed: bool = field(default_factory=lambda: _env_bool("LLAMA_CPP_MANAGED", False))
    llama_cpp_model_name: str | None = field(default_factory=lambda: _env_str("LLAMA_CPP_MODEL_NAME"))
    llama_cpp_timeout_seconds: float = field(
        default_factory=lambda: _env_float("LLAMA_CPP_TIMEOUT_SECONDS") or 30.0
    )
    use_ollama: bool = field(default_factory=lambda: _env_bool("USE_OLLAMA", False))
    ollama_base_url: str = field(
        default_factory=lambda: _env_str("OLLAMA_BASE_URL")
        or _env_str("JARVISV7_OLLAMA_URL")
        or "http://127.0.0.1:11434"
    )
    ollama_model: str | None = field(default_factory=lambda: _env_str("OLLAMA_MODEL", "phi4-mini"))
    ollama_num_ctx: int | None = field(default_factory=lambda: _env_int("OLLAMA_NUM_CTX") or 8192)
    live_tests: bool = field(default_factory=lambda: _env_bool("JARVISV7_LIVE_TESTS", False))
    tts_models: str | None = field(default_factory=lambda: _env_str("TTS_MODELS", "models/tts"))
    stt_models: str | None = field(default_factory=lambda: _env_str("STT_MODELS", "models/stt"))
    wake_model: str | None = field(default_factory=lambda: _env_str("WAKE_MODEL", "models/wake"))
    resident_voice_speech_rms_threshold: float = field(
        default_factory=lambda: _env_float("RESIDENT_VOICE_SPEECH_RMS_THRESHOLD") or 0.02
    )
    resident_voice_no_speech_timeout_seconds: float = field(
        default_factory=lambda: _env_float("RESIDENT_VOICE_NO_SPEECH_TIMEOUT_SECONDS") or 5.0
    )
    resident_voice_silence_end_seconds: float = field(
        default_factory=lambda: _env_float("RESIDENT_VOICE_SILENCE_END_SECONDS") or 0.5
    )
    resident_voice_max_duration_seconds: float = field(
        default_factory=lambda: _env_float("RESIDENT_VOICE_MAX_DURATION_SECONDS") or 8.0
    )
    resident_voice_pre_roll_seconds: float = field(
        default_factory=lambda: _env_float("RESIDENT_VOICE_PRE_ROLL_SECONDS") or 0.25
    )
    resident_voice_min_speech_seconds: float = field(
        default_factory=lambda: _env_float("RESIDENT_VOICE_MIN_SPEECH_SECONDS") or 0.2
    )
    qairt_sdk_path: str | None = field(default_factory=lambda: _env_str("QAIRT_SDK_PATH"))
    picovoice_access_key: str | None = field(
        default_factory=lambda: _env_str("PICOVOICE_ACCESS_KEY")
    )
    pvporcupine_model_path: str | None = field(
        default_factory=lambda: _env_str("PVPORCUPINE_MODEL_PATH")
    )
    redis_host: str = field(default_factory=lambda: _env_str("REDIS_HOST", "127.0.0.1") or "127.0.0.1")
    redis_port: int = field(default_factory=lambda: _env_int("REDIS_PORT") or 6379)
    redis_db: int = field(default_factory=lambda: _env_int("REDIS_DB") or 0)
    redis_max_connections: int = field(
        default_factory=lambda: _env_int("REDIS_MAX_CONNECTIONS") or 10
    )
    redis_socket_timeout: float = field(
        default_factory=lambda: _env_float("REDIS_SOCKET_TIMEOUT") or 2.0
    )
    use_searxng: bool = field(default_factory=lambda: _env_bool("USE_SEARXNG", False))
    searxng_port: int = field(default_factory=lambda: _env_int("SEARXNG_PORT") or 8888)
    searxng_base_url: str = field(
        default_factory=lambda: _env_str("SEARXNG_BASE_URL")
        or _endpoint_url_from_host_port("127.0.0.1", _env_int("SEARXNG_PORT") or 8888)
    )
    use_ddgs: bool = field(default_factory=lambda: _env_bool("USE_DDGS", True))
    use_tavily: bool = field(default_factory=lambda: _env_bool("USE_TAVILY", False))
    tavily_api_key: str = field(default_factory=lambda: _env_str("TAVILY_API_KEY", "") or "")

    @property
    def effective_local_model_fetch(self) -> bool:
        if self.local_model_fetch_explicit:
            return self.local_model_fetch
        return self.use_local_model

    @property
    def effective_llama_cpp_managed(self) -> bool:
        if self.llama_cpp_managed_explicit:
            return self.llama_cpp_managed
        return self.use_local_model


def load_settings() -> Settings:
    _load_dotenv_if_present()
    return Settings()
