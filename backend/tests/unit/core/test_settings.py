from __future__ import annotations

import importlib
from pathlib import Path


ENV_NAMES = (
    "APP_NAME",
    "JARVIS_LANGUAGE",
    "CONFIG_PATH",
    "DATA_PATH",
    "MODEL_PATH",
    "USE_LOCAL_MODEL",
    "LOCAL_MODEL_FETCH",
    "LLAMA_CPP_MODEL_PATH",
    "LLAMA_CPP_BASE_URL",
    "LLAMA_CPP_HOST",
    "LLAMA_CPP_PORT",
    "LLAMA_CPP_BINARY_PATH",
    "LLAMA_CPP_MANAGED",
    "LLAMA_CPP_MODEL_NAME",
    "LLAMA_CPP_TIMEOUT_SECONDS",
    "USE_OLLAMA",
    "OLLAMA_BASE_URL",
    "JARVISV7_OLLAMA_URL",
    "OLLAMA_MODEL",
    "OLLAMA_NUM_CTX",
    "JARVISV7_LIVE_TESTS",
    "TTS_MODELS",
    "STT_MODELS",
    "WAKE_MODEL",
    "QAIRT_SDK_PATH",
    "PICOVOICE_ACCESS_KEY",
    "PVPORCUPINE_MODEL_PATH",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_MAX_CONNECTIONS",
    "REDIS_SOCKET_TIMEOUT",
    "USE_SEARXNG",
    "SEARXNG_BASE_URL",
    "USE_DDGS",
    "USE_TAVILY",
    "TAVILY_API_KEY",
)

ENV_EXAMPLE_REQUIRED_NAMES: set[str] = {
    "APP_NAME",
    "JARVIS_LANGUAGE",
    "CONFIG_PATH",
    "DATA_PATH",
    "MODEL_PATH",
    "USE_LOCAL_MODEL",
    "LOCAL_MODEL_FETCH",
    "LLAMA_CPP_MODEL_PATH",
    "LLAMA_CPP_BASE_URL",
    "LLAMA_CPP_HOST",
    "LLAMA_CPP_PORT",
    "LLAMA_CPP_BINARY_PATH",
    "LLAMA_CPP_MANAGED",
    "LLAMA_CPP_MODEL_NAME",
    "LLAMA_CPP_TIMEOUT_SECONDS",
    "USE_OLLAMA",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_NUM_CTX",
    "JARVISV7_LIVE_TESTS",
    "TTS_MODELS",
    "STT_MODELS",
    "WAKE_MODEL",
    "QAIRT_SDK_PATH",
    "PICOVOICE_ACCESS_KEY",
    "PVPORCUPINE_MODEL_PATH",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_MAX_CONNECTIONS",
    "REDIS_SOCKET_TIMEOUT",
    "USE_SEARXNG",
    "SEARXNG_BASE_URL",
    "USE_DDGS",
    "USE_TAVILY",
    "TAVILY_API_KEY",
}

ENV_EXAMPLE_COMPATIBILITY_ALIAS_NAMES: set[str] = {
    "JARVISV7_OLLAMA_URL",
}


def _reload_settings(monkeypatch, tmp_path, env_text: str | None, example_text: str | None):
    settings_module = importlib.import_module("backend.app.core.settings")
    env_path = tmp_path / ".env"
    example_path = tmp_path / ".env.example"
    if env_text is not None:
        env_path.write_text(env_text, encoding="utf-8")
    if example_text is not None:
        example_path.write_text(example_text, encoding="utf-8")
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings_module, "ENV_FILE", env_path)
    monkeypatch.setattr(settings_module, "ENV_EXAMPLE_FILE", example_path)
    return settings_module


def test_settings_prefer_env_file_over_shell_env_when_env_file_exists(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "JARVIS_LANGUAGE=fr\nOLLAMA_BASE_URL=http://env-file:11434\nOLLAMA_MODEL=env-file-model\nOLLAMA_NUM_CTX=2048\nJARVISV7_LIVE_TESTS=false\n",
        "OLLAMA_BASE_URL=http://example-file:11434\nOLLAMA_MODEL=example-model\nOLLAMA_NUM_CTX=1024\nJARVISV7_LIVE_TESTS=false\n",
    )
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://shell:11434")
    monkeypatch.setenv("JARVIS_LANGUAGE", "pl")
    monkeypatch.setenv("OLLAMA_MODEL", "shell-model")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "8192")
    monkeypatch.setenv("JARVISV7_LIVE_TESTS", "true")

    settings = settings_module.load_settings()

    assert settings.jarvis_language == "fr"
    assert settings.ollama_base_url == "http://env-file:11434"
    assert settings.ollama_model == "env-file-model"
    assert settings.ollama_num_ctx == 2048
    assert settings.live_tests is False


def test_settings_load_env_over_env_example_when_shell_env_absent(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "OLLAMA_BASE_URL=http://env-file:11434\nOLLAMA_MODEL=env-file-model\nOLLAMA_NUM_CTX=4096\nJARVISV7_LIVE_TESTS=yes\n",
        "OLLAMA_BASE_URL=http://example-file:11434\nOLLAMA_MODEL=example-model\nOLLAMA_NUM_CTX=1024\nJARVISV7_LIVE_TESTS=false\n",
    )

    settings = settings_module.load_settings()

    assert settings.ollama_base_url == "http://env-file:11434"
    assert settings.ollama_model == "env-file-model"
    assert settings.ollama_num_ctx == 4096
    assert settings.live_tests is True


def test_settings_load_env_example_when_env_absent(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        None,
        "OLLAMA_BASE_URL=http://example-file:11434\nOLLAMA_MODEL=example-model\nOLLAMA_NUM_CTX=1024\nJARVISV7_LIVE_TESTS=on\n",
    )

    settings = settings_module.load_settings()

    assert settings.ollama_base_url == "http://example-file:11434"
    assert settings.ollama_model == "example-model"
    assert settings.ollama_num_ctx == 1024
    assert settings.live_tests is True


def test_settings_prefer_ollama_base_url_over_legacy_alias(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "OLLAMA_BASE_URL=http://canonical:11434\nJARVISV7_OLLAMA_URL=http://legacy:11434\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.ollama_base_url == "http://canonical:11434"


def test_settings_allow_legacy_jarvisv7_ollama_url_alias(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "JARVISV7_OLLAMA_URL=http://legacy:11434\nOLLAMA_MODEL=env-model\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.ollama_base_url == "http://legacy:11434"
    assert settings.ollama_model == "env-model"


def test_llama_cpp_sidecar_settings_read_from_env(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "\n".join(
            [
                "LLAMA_CPP_MODEL_PATH=models/llm/dev/model.gguf",
                "LLAMA_CPP_BASE_URL=http://127.0.0.1:18080",
                "LLAMA_CPP_HOST=127.0.0.2",
                "LLAMA_CPP_PORT=18080",
                "LLAMA_CPP_BINARY_PATH=runtimes/llama.cpp/llama-server.exe",
                "LLAMA_CPP_MANAGED=true",
                "LLAMA_CPP_MODEL_NAME=dev-q4",
                "LLAMA_CPP_TIMEOUT_SECONDS=12.5",
            ]
        )
        + "\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.llama_cpp_model_path == "models/llm/dev/model.gguf"
    assert settings.llama_cpp_base_url == "http://127.0.0.1:18080"
    assert settings.llama_cpp_host == "127.0.0.2"
    assert settings.llama_cpp_port == 18080
    assert settings.llama_cpp_binary_path == "runtimes/llama.cpp/llama-server.exe"
    assert settings.llama_cpp_managed is True
    assert settings.llama_cpp_model_name == "dev-q4"
    assert settings.llama_cpp_timeout_seconds == 12.5


def test_llama_cpp_sidecar_settings_use_defaults_when_env_absent(monkeypatch, tmp_path):
    settings_module = _reload_settings(monkeypatch, tmp_path, None, None)

    settings = settings_module.load_settings()

    assert settings.llama_cpp_base_url == "http://127.0.0.1:8080"
    assert settings.llama_cpp_host == "127.0.0.1"
    assert settings.llama_cpp_port == 8080
    assert settings.llama_cpp_binary_path is None
    assert settings.llama_cpp_managed is False
    assert settings.llama_cpp_model_name is None
    assert settings.llama_cpp_timeout_seconds == 30.0


def test_redis_settings_read_from_env(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "REDIS_HOST=10.0.0.8\nREDIS_PORT=6380\nREDIS_DB=2\nREDIS_MAX_CONNECTIONS=42\nREDIS_SOCKET_TIMEOUT=1.5\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.redis_host == "10.0.0.8"
    assert settings.redis_port == 6380
    assert settings.redis_db == 2
    assert settings.redis_max_connections == 42
    assert settings.redis_socket_timeout == 1.5


def test_redis_settings_use_defaults_when_env_absent(monkeypatch, tmp_path):
    settings_module = _reload_settings(monkeypatch, tmp_path, None, None)

    settings = settings_module.load_settings()

    assert settings.redis_host == "127.0.0.1"
    assert settings.redis_port == 6379
    assert settings.redis_db == 0
    assert settings.redis_max_connections == 10
    assert settings.redis_socket_timeout == 2.0


def test_search_settings_read_from_env(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "USE_SEARXNG=false\nSEARXNG_BASE_URL=http://searxng:9999\nUSE_DDGS=no\nUSE_TAVILY=1\nTAVILY_API_KEY=test-key\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.use_searxng is False
    assert settings.searxng_base_url == "http://searxng:9999"
    assert settings.use_ddgs is False
    assert settings.use_tavily is True
    assert settings.tavily_api_key == "test-key"


def test_search_settings_use_defaults_when_env_absent(monkeypatch, tmp_path):
    settings_module = _reload_settings(monkeypatch, tmp_path, None, None)

    settings = settings_module.load_settings()

    assert settings.use_searxng is True
    assert settings.searxng_base_url == "http://127.0.0.1:8888"
    assert settings.use_ddgs is True
    assert settings.use_tavily is False
    assert settings.tavily_api_key == ""


def test_search_bool_settings_parse_common_truthy_falsey_values(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "USE_SEARXNG=on\nUSE_DDGS=off\nUSE_TAVILY=yes\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.use_searxng is True
    assert settings.use_ddgs is False
    assert settings.use_tavily is True


def _parse_env_template(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        values[name.strip()] = value.strip()
    return values


def test_env_example_covers_current_settings_env_variables():
    values = _parse_env_template(Path(".env.example"))

    missing = sorted(ENV_EXAMPLE_REQUIRED_NAMES - set(values))
    assert missing == []
    advertised_aliases = sorted(ENV_EXAMPLE_COMPATIBILITY_ALIAS_NAMES & set(values))
    assert advertised_aliases == []
    assert values["OLLAMA_BASE_URL"]
    assert values["JARVIS_LANGUAGE"] == "english"
    assert values["OLLAMA_MODEL"]
    assert values["OLLAMA_NUM_CTX"]
    assert values["LLAMA_CPP_BASE_URL"] == "http://127.0.0.1:8080"
    assert values["LLAMA_CPP_HOST"] == "127.0.0.1"
    assert values["LLAMA_CPP_PORT"] == "8080"
    assert values["LLAMA_CPP_MODEL_NAME"] == "assistant-small-q4"
    assert values["LLAMA_CPP_TIMEOUT_SECONDS"] == "30"
    assert values["SEARXNG_BASE_URL"] == "http://127.0.0.1:8888"
    assert values["JARVISV7_LIVE_TESTS"].lower() in {"0", "1", "false", "true", "no", "yes", "off", "on"}
    assert values["LOCAL_MODEL_FETCH"].lower() in {"0", "1", "false", "true", "no", "yes", "off", "on"}
    assert values["LLAMA_CPP_MANAGED"].lower() in {"0", "1", "false", "true", "no", "yes", "off", "on"}
    assert values["PICOVOICE_ACCESS_KEY"] in {"", "<placeholder>", "<secret>"}
