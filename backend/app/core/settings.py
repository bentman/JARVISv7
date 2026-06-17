from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.core.paths import CONFIG_DIR, DATA_DIR, MODELS_DIR, REPO_ROOT


ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE_FILE = REPO_ROOT / ".env.example"


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
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


@dataclass(slots=True)
class Settings:
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "JARVISv7"))
    config_path: Path = field(
        default_factory=lambda: Path(os.getenv("CONFIG_PATH", str(CONFIG_DIR)))
    )
    data_path: Path = field(default_factory=lambda: Path(os.getenv("DATA_PATH", str(DATA_DIR))))
    tool_filesystem_sandbox_path: Path = field(
        default_factory=lambda: Path(os.getenv("TOOL_FILESYSTEM_SANDBOX_PATH", "data/tool_sandbox/"))
    )
    model_path: Path = field(default_factory=lambda: Path(os.getenv("MODEL_PATH", str(MODELS_DIR))))
    use_local_model: bool = field(default_factory=lambda: _env_bool("USE_LOCAL_MODEL", False))
    local_model_fetch: bool = field(default_factory=lambda: _env_bool("LOCAL_MODEL_FETCH", False))
    llama_cpp_model_path: str | None = field(
        default_factory=lambda: os.getenv("LLAMA_CPP_MODEL_PATH")
    )
    llama_cpp_base_url: str = field(
        default_factory=lambda: os.getenv("LLAMA_CPP_BASE_URL", "http://127.0.0.1:8080")
    )
    llama_cpp_host: str = field(default_factory=lambda: os.getenv("LLAMA_CPP_HOST", "127.0.0.1"))
    llama_cpp_port: int = field(default_factory=lambda: _env_int("LLAMA_CPP_PORT") or 8080)
    llama_cpp_binary_path: str | None = field(
        default_factory=lambda: os.getenv("LLAMA_CPP_BINARY_PATH")
    )
    llama_cpp_managed: bool = field(default_factory=lambda: _env_bool("LLAMA_CPP_MANAGED", False))
    llama_cpp_model_name: str | None = field(default_factory=lambda: os.getenv("LLAMA_CPP_MODEL_NAME"))
    llama_cpp_timeout_seconds: float = field(
        default_factory=lambda: _env_float("LLAMA_CPP_TIMEOUT_SECONDS") or 30.0
    )
    use_ollama: bool = field(default_factory=lambda: _env_bool("USE_OLLAMA", False))
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL")
        or os.getenv("JARVISV7_OLLAMA_URL")
        or "http://127.0.0.1:11434"
    )
    ollama_model: str | None = field(default_factory=lambda: os.getenv("OLLAMA_MODEL"))
    ollama_num_ctx: int | None = field(default_factory=lambda: _env_int("OLLAMA_NUM_CTX"))
    live_tests: bool = field(default_factory=lambda: _env_bool("JARVISV7_LIVE_TESTS", False))
    tts_models: str | None = field(default_factory=lambda: os.getenv("TTS_MODELS"))
    stt_models: str | None = field(default_factory=lambda: os.getenv("STT_MODELS"))
    wake_model: str | None = field(default_factory=lambda: os.getenv("WAKE_MODEL"))
    qairt_sdk_path: str | None = field(default_factory=lambda: os.getenv("QAIRT_SDK_PATH"))
    picovoice_access_key: str | None = field(
        default_factory=lambda: os.getenv("PICOVOICE_ACCESS_KEY")
    )
    pvporcupine_model_path: str | None = field(
        default_factory=lambda: os.getenv("PVPORCUPINE_MODEL_PATH")
    )
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "127.0.0.1"))
    redis_port: int = field(default_factory=lambda: _env_int("REDIS_PORT") or 6379)
    redis_db: int = field(default_factory=lambda: _env_int("REDIS_DB") or 0)
    redis_max_connections: int = field(
        default_factory=lambda: _env_int("REDIS_MAX_CONNECTIONS") or 10
    )
    redis_socket_timeout: float = field(
        default_factory=lambda: _env_float("REDIS_SOCKET_TIMEOUT") or 2.0
    )
    use_searxng: bool = field(default_factory=lambda: _env_bool("USE_SEARXNG", True))
    searxng_base_url: str = field(
        default_factory=lambda: os.getenv("SEARXNG_BASE_URL", "http://127.0.0.1:8888")
    )
    use_ddgs: bool = field(default_factory=lambda: _env_bool("USE_DDGS", True))
    use_tavily: bool = field(default_factory=lambda: _env_bool("USE_TAVILY", False))
    tavily_api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))


def load_settings() -> Settings:
    _load_dotenv_if_present()
    return Settings()
