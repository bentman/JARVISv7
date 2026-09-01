from __future__ import annotations

import os
from dataclasses import dataclass

from backend.app.core.paths import REPO_ROOT

ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE_FILE = REPO_ROOT / ".env.example"

SETTING_ENV_CLASSIFICATION: dict[str, str] = {
    "JARVIS_LANGUAGE": "primary",
    "USE_LOCAL_MODEL": "primary",
    "LLM_MODEL_MODE": "primary",
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
    "LLAMA_CPP_CONTEXT_SIZE": "advanced",
    "JARVIS_SECRET_STORE_KEY": "secret",
    "JARVIS_SECRET_STORE_PREVIOUS_KEY": "secret",
    "USE_OLLAMA": "primary",
    "OLLAMA_BASE_URL": "advanced",
    "JARVISV7_OLLAMA_URL": "compatibility",
    "OLLAMA_MODEL": "primary",
    "OLLAMA_NUM_CTX": "advanced",
    "OLLAMA_KEEP_ALIVE": "advanced",
    "JARVISV7_LIVE_TESTS": "test-only",
    "RESIDENT_VOICE_SPEECH_RMS_THRESHOLD": "advanced",
    "RESIDENT_VOICE_NO_SPEECH_TIMEOUT_SECONDS": "advanced",
    "RESIDENT_VOICE_SILENCE_END_SECONDS": "advanced",
    "RESIDENT_VOICE_MAX_DURATION_SECONDS": "advanced",
    "RESIDENT_VOICE_PRE_ROLL_SECONDS": "advanced",
    "RESIDENT_VOICE_MIN_SPEECH_SECONDS": "advanced",
    "QAIRT_SDK_PATH": "advanced",
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


def _env_choice(name: str, choices: set[str], default: str) -> str:
    value = _env_str(name, default)
    assert value is not None
    selected = value.strip()
    if selected not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of: {allowed}")
    return selected


def _endpoint_url_from_host_port(host: str, port: int) -> str:
    return f"http://{host}:{port}"


@dataclass(slots=True)
class Settings:
    """Static, environment-independent defaults. Use load_settings() to read .env/.env.example."""

    jarvis_language: str = "english"
    use_local_model: bool = True
    local_model_fetch_explicit: bool = False
    local_model_fetch: bool = False
    llm_model_mode: str = "dev"
    llm_model_policy: str | None = "auto"
    llm_model_id: str | None = None
    llama_cpp_model_path: str | None = None
    llama_cpp_base_url: str = "http://127.0.0.1:8080"
    llama_cpp_base_url_explicit: bool = False
    llama_cpp_host: str = "127.0.0.1"
    llama_cpp_port: int = 8080
    llama_cpp_binary_path: str | None = None
    llama_cpp_managed_explicit: bool = False
    llama_cpp_managed: bool = False
    llama_cpp_model_name: str | None = None
    llama_cpp_timeout_seconds: float = 30.0
    llama_cpp_context_size: int = 2048
    jarvis_secret_store_key: str | None = None
    jarvis_secret_store_previous_key: str | None = None
    use_ollama: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str | None = "phi4-mini"
    ollama_num_ctx: int | None = 8192
    ollama_keep_alive: str = "5m"
    live_tests: bool = False
    resident_voice_speech_rms_threshold: float = 0.02
    resident_voice_no_speech_timeout_seconds: float = 5.0
    resident_voice_silence_end_seconds: float = 0.5
    resident_voice_max_duration_seconds: float = 8.0
    resident_voice_pre_roll_seconds: float = 0.25
    resident_voice_min_speech_seconds: float = 0.2
    qairt_sdk_path: str | None = None
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_max_connections: int = 10
    redis_socket_timeout: float = 2.0
    use_searxng: bool = False
    searxng_port: int = 8888
    searxng_base_url: str = "http://127.0.0.1:8888"
    use_ddgs: bool = True
    use_tavily: bool = False
    tavily_api_key: str = ""

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
    """Build Settings from .env (or .env.example when .env is absent), overriding the static defaults above."""
    _load_dotenv_if_present()

    llama_cpp_host = _env_str("LLAMA_CPP_HOST", "127.0.0.1") or "127.0.0.1"
    llama_cpp_port = _env_int("LLAMA_CPP_PORT") or 8080
    llama_cpp_base_url = _env_str("LLAMA_CPP_BASE_URL") or _endpoint_url_from_host_port(llama_cpp_host, llama_cpp_port)
    searxng_port = _env_int("SEARXNG_PORT") or 8888
    searxng_base_url = _env_str("SEARXNG_BASE_URL") or _endpoint_url_from_host_port("127.0.0.1", searxng_port)
    ollama_base_url = _env_str("OLLAMA_BASE_URL") or _env_str("JARVISV7_OLLAMA_URL") or "http://127.0.0.1:11434"

    return Settings(
        jarvis_language=_env_str("JARVIS_LANGUAGE", "english") or "english",
        use_local_model=_env_bool("USE_LOCAL_MODEL", True),
        local_model_fetch_explicit=_env_present("LOCAL_MODEL_FETCH"),
        local_model_fetch=_env_bool("LOCAL_MODEL_FETCH", False),
        llm_model_mode=_env_choice("LLM_MODEL_MODE", {"dev", "prod"}, "dev"),
        llm_model_policy=_env_str("LLM_MODEL_POLICY", "auto"),
        llm_model_id=_env_str("LLM_MODEL_ID"),
        llama_cpp_model_path=_env_str("LLAMA_CPP_MODEL_PATH"),
        llama_cpp_base_url=llama_cpp_base_url,
        llama_cpp_base_url_explicit=_env_present("LLAMA_CPP_BASE_URL"),
        llama_cpp_host=llama_cpp_host,
        llama_cpp_port=llama_cpp_port,
        llama_cpp_binary_path=_env_str("LLAMA_CPP_BINARY_PATH"),
        llama_cpp_managed_explicit=_env_present("LLAMA_CPP_MANAGED"),
        llama_cpp_managed=_env_bool("LLAMA_CPP_MANAGED", False),
        llama_cpp_model_name=_env_str("LLAMA_CPP_MODEL_NAME"),
        llama_cpp_timeout_seconds=_env_float("LLAMA_CPP_TIMEOUT_SECONDS") or 30.0,
        llama_cpp_context_size=_env_int("LLAMA_CPP_CONTEXT_SIZE") or 2048,
        jarvis_secret_store_key=_env_str("JARVIS_SECRET_STORE_KEY"),
        jarvis_secret_store_previous_key=_env_str("JARVIS_SECRET_STORE_PREVIOUS_KEY"),
        use_ollama=_env_bool("USE_OLLAMA", False),
        ollama_base_url=ollama_base_url,
        ollama_model=_env_str("OLLAMA_MODEL", "phi4-mini"),
        ollama_num_ctx=_env_int("OLLAMA_NUM_CTX") or 8192,
        ollama_keep_alive=_env_str("OLLAMA_KEEP_ALIVE", "5m") or "5m",
        live_tests=_env_bool("JARVISV7_LIVE_TESTS", False),
        resident_voice_speech_rms_threshold=_env_float("RESIDENT_VOICE_SPEECH_RMS_THRESHOLD") or 0.02,
        resident_voice_no_speech_timeout_seconds=_env_float("RESIDENT_VOICE_NO_SPEECH_TIMEOUT_SECONDS") or 5.0,
        resident_voice_silence_end_seconds=_env_float("RESIDENT_VOICE_SILENCE_END_SECONDS") or 0.5,
        resident_voice_max_duration_seconds=_env_float("RESIDENT_VOICE_MAX_DURATION_SECONDS") or 8.0,
        resident_voice_pre_roll_seconds=_env_float("RESIDENT_VOICE_PRE_ROLL_SECONDS") or 0.25,
        resident_voice_min_speech_seconds=_env_float("RESIDENT_VOICE_MIN_SPEECH_SECONDS") or 0.2,
        qairt_sdk_path=_env_str("QAIRT_SDK_PATH"),
        redis_host=_env_str("REDIS_HOST", "127.0.0.1") or "127.0.0.1",
        redis_port=_env_int("REDIS_PORT") or 6379,
        redis_db=_env_int("REDIS_DB") or 0,
        redis_max_connections=_env_int("REDIS_MAX_CONNECTIONS") or 10,
        redis_socket_timeout=_env_float("REDIS_SOCKET_TIMEOUT") or 2.0,
        use_searxng=_env_bool("USE_SEARXNG", False),
        searxng_port=searxng_port,
        searxng_base_url=searxng_base_url,
        use_ddgs=_env_bool("USE_DDGS", True),
        use_tavily=_env_bool("USE_TAVILY", False),
        tavily_api_key=_env_str("TAVILY_API_KEY", "") or "",
    )
