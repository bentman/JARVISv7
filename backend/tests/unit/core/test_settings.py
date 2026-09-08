from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ENV_NAMES = (
    "JARVIS_LANGUAGE",
    "USE_LOCAL_MODEL",
    "LLM_MODEL_MODE",
    "LLM_MODEL_POLICY",
    "LLM_MODEL_ID",
    "LOCAL_MODEL_FETCH",
    "LLAMA_CPP_MODEL_PATH",
    "LLAMA_CPP_BASE_URL",
    "LLAMA_CPP_HOST",
    "LLAMA_CPP_PORT",
    "LLAMA_CPP_BINARY_PATH",
    "LLAMA_CPP_MANAGED",
    "LLAMA_CPP_MODEL_NAME",
    "LLAMA_CPP_TIMEOUT_SECONDS",
    "LLAMA_CPP_CONTEXT_SIZE",
    "JARVIS_SECRET_STORE_KEY",
    "JARVIS_SECRET_STORE_PREVIOUS_KEY",
    "USE_OLLAMA",
    "OLLAMA_BASE_URL",
    "JARVISV7_OLLAMA_URL",
    "OLLAMA_MODEL",
    "OLLAMA_NUM_CTX",
    "OLLAMA_KEEP_ALIVE",
    "JARVISV7_LIVE_TESTS",
    "RESIDENT_VOICE_SPEECH_RMS_THRESHOLD",
    "RESIDENT_VOICE_NO_SPEECH_TIMEOUT_SECONDS",
    "RESIDENT_VOICE_SILENCE_END_SECONDS",
    "RESIDENT_VOICE_MAX_DURATION_SECONDS",
    "RESIDENT_VOICE_PRE_ROLL_SECONDS",
    "RESIDENT_VOICE_MIN_SPEECH_SECONDS",
    "QAIRT_SDK_PATH",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_MAX_CONNECTIONS",
    "REDIS_SOCKET_TIMEOUT",
    "USE_SEARXNG",
    "SEARXNG_PORT",
    "SEARXNG_BASE_URL",
    "USE_DDGS",
    "USE_TAVILY",
    "TAVILY_API_KEY",
)

RETIRED_SETTING_NAMES = {
    "APP_NAME",
    "CONFIG_PATH",
    "DATA_PATH",
    "MODEL_PATH",
    "STT_MODELS",
    "TTS_MODELS",
    "WAKE_MODEL",
}

ENV_EXAMPLE_REQUIRED_NAMES: set[str] = {
    "JARVIS_LANGUAGE",
    "USE_LOCAL_MODEL",
    "LLM_MODEL_MODE",
    "LLM_MODEL_POLICY",
    "LLM_MODEL_ID",
    "USE_OLLAMA",
    "OLLAMA_MODEL",
    "USE_SEARXNG",
    "SEARXNG_PORT",
    "USE_DDGS",
    "USE_TAVILY",
    "TAVILY_API_KEY",
    "JARVIS_SECRET_STORE_KEY",
    "REDIS_HOST",
    "REDIS_PORT",
}

ENV_EXAMPLE_COMPATIBILITY_ALIAS_NAMES: set[str] = {
    "JARVISV7_OLLAMA_URL",
}

ENV_EXAMPLE_ADVANCED_NAMES: set[str] = {
    "LOCAL_MODEL_FETCH",
    "LLAMA_CPP_MODEL_PATH",
    "LLAMA_CPP_HOST",
    "LLAMA_CPP_PORT",
    "LLAMA_CPP_BINARY_PATH",
    "LLAMA_CPP_TIMEOUT_SECONDS",
    "OLLAMA_BASE_URL",
    "OLLAMA_NUM_CTX",
    "OLLAMA_KEEP_ALIVE",
    "JARVISV7_LIVE_TESTS",
    "RESIDENT_VOICE_SPEECH_RMS_THRESHOLD",
    "RESIDENT_VOICE_NO_SPEECH_TIMEOUT_SECONDS",
    "RESIDENT_VOICE_SILENCE_END_SECONDS",
    "RESIDENT_VOICE_MAX_DURATION_SECONDS",
    "RESIDENT_VOICE_PRE_ROLL_SECONDS",
    "RESIDENT_VOICE_MIN_SPEECH_SECONDS",
    "QAIRT_SDK_PATH",
    "REDIS_DB",
    "REDIS_MAX_CONNECTIONS",
    "REDIS_SOCKET_TIMEOUT",
    "SEARXNG_BASE_URL",
}

ENV_EXAMPLE_EXTERNAL_LLAMA_CPP_NAMES: set[str] = {
    "LLAMA_CPP_MANAGED",
    "LLAMA_CPP_BASE_URL",
    "LLAMA_CPP_MODEL_NAME",
    "LLAMA_CPP_CONTEXT_SIZE",
}

ENV_EXAMPLE_UNIMPLEMENTED_NAMES: set[str] = {
    "APP_NAME",
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


_ENV_FILE_CONTENT = "OLLAMA_BASE_URL=http://env-file:11434\nOLLAMA_MODEL=env-file-model\nOLLAMA_NUM_CTX=4096\nOLLAMA_KEEP_ALIVE=15m\nJARVISV7_LIVE_TESTS=yes\n"
_EXAMPLE_FILE_CONTENT = "OLLAMA_BASE_URL=http://example-file:11434\nOLLAMA_MODEL=example-model\nOLLAMA_NUM_CTX=1024\nOLLAMA_KEEP_ALIVE=2m\nJARVISV7_LIVE_TESTS=on\n"


@pytest.mark.parametrize(
    ("shell_env", "env_content", "expected"),
    [
        pytest.param(
            {
                "OLLAMA_BASE_URL": "http://shell:11434",
                "JARVIS_LANGUAGE": "pl",
                "OLLAMA_MODEL": "shell-model",
                "OLLAMA_NUM_CTX": "8192",
                "OLLAMA_KEEP_ALIVE": "30m",
                "JARVISV7_LIVE_TESTS": "true",
            },
            "JARVIS_LANGUAGE=fr\nOLLAMA_BASE_URL=http://env-file:11434\nOLLAMA_MODEL=env-file-model\nOLLAMA_NUM_CTX=2048\nOLLAMA_KEEP_ALIVE=10m\nJARVISV7_LIVE_TESTS=false\n",
            {"ollama_base_url": "http://shell:11434", "ollama_model": "shell-model", "ollama_num_ctx": 8192, "ollama_keep_alive": "30m", "live_tests": True},
            id="shell-env-over-env-file",
        ),
        pytest.param(
            None,
            _ENV_FILE_CONTENT,
            {"ollama_base_url": "http://env-file:11434", "ollama_model": "env-file-model", "ollama_num_ctx": 4096, "ollama_keep_alive": "15m", "live_tests": True},
            id="env-file-over-env-example-when-shell-absent",
        ),
        pytest.param(
            None,
            None,
            {"ollama_base_url": "http://example-file:11434", "ollama_model": "example-model", "ollama_num_ctx": 1024, "ollama_keep_alive": "2m", "live_tests": True},
            id="env-example-when-env-absent",
        ),
    ],
)
def test_settings_precedence_across_shell_env_and_dotenv_files(monkeypatch, tmp_path, shell_env, env_content, expected):
    settings_module = _reload_settings(monkeypatch, tmp_path, env_content, _EXAMPLE_FILE_CONTENT)
    for name, value in (shell_env or {}).items():
        monkeypatch.setenv(name, value)

    settings = settings_module.load_settings()

    assert settings.ollama_base_url == expected["ollama_base_url"]
    assert settings.ollama_model == expected["ollama_model"]
    assert settings.ollama_num_ctx == expected["ollama_num_ctx"]
    assert settings.ollama_keep_alive == expected["ollama_keep_alive"]
    assert settings.live_tests == expected["live_tests"]
    if shell_env and "JARVIS_LANGUAGE" in shell_env:
        assert settings.jarvis_language == shell_env["JARVIS_LANGUAGE"]


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
    assert settings.llama_cpp_managed_explicit is False
    assert settings.effective_llama_cpp_managed is True
    assert settings.local_model_fetch is False
    assert settings.local_model_fetch_explicit is False
    assert settings.effective_local_model_fetch is True
    assert settings.llama_cpp_model_name is None
    assert settings.llama_cpp_timeout_seconds == 30.0


def test_local_model_intent_derives_fetch_and_managed_sidecar_when_overrides_absent(monkeypatch, tmp_path):
    settings_module = _reload_settings(monkeypatch, tmp_path, "USE_LOCAL_MODEL=true\n", None)

    settings = settings_module.load_settings()

    assert settings.use_local_model is True
    assert settings.local_model_fetch is False
    assert settings.local_model_fetch_explicit is False
    assert settings.effective_local_model_fetch is True
    assert settings.llama_cpp_managed is False
    assert settings.llama_cpp_managed_explicit is False
    assert settings.effective_llama_cpp_managed is True


def test_explicit_local_model_fetch_and_sidecar_overrides_win_over_local_model_intent(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "USE_LOCAL_MODEL=true\nLOCAL_MODEL_FETCH=false\nLLAMA_CPP_MANAGED=false\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.local_model_fetch_explicit is True
    assert settings.effective_local_model_fetch is False
    assert settings.llama_cpp_managed_explicit is True
    assert settings.effective_llama_cpp_managed is False


def test_llama_cpp_base_url_derives_from_host_and_port_when_base_url_absent(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "LLAMA_CPP_HOST=127.0.0.2\nLLAMA_CPP_PORT=18080\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.llama_cpp_base_url == "http://127.0.0.2:18080"


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
        "USE_SEARXNG=false\nSEARXNG_PORT=9999\nSEARXNG_BASE_URL=http://searxng:9999\nUSE_DDGS=no\nUSE_TAVILY=1\nTAVILY_API_KEY=test-key\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.use_searxng is False
    assert settings.searxng_port == 9999
    assert settings.searxng_base_url == "http://searxng:9999"
    assert settings.use_ddgs is False
    assert settings.use_tavily is True
    assert settings.tavily_api_key == "test-key"


def test_search_settings_use_defaults_when_env_absent(monkeypatch, tmp_path):
    settings_module = _reload_settings(monkeypatch, tmp_path, None, None)

    settings = settings_module.load_settings()

    assert settings.use_searxng is False
    assert settings.searxng_port == 8888
    assert settings.searxng_base_url == "http://127.0.0.1:8888"
    assert settings.use_ddgs is True
    assert settings.use_tavily is False
    assert settings.tavily_api_key == ""


def test_search_base_url_derives_from_searxng_port_when_base_url_absent(monkeypatch, tmp_path):
    settings_module = _reload_settings(monkeypatch, tmp_path, "SEARXNG_PORT=9999\n", None)

    settings = settings_module.load_settings()

    assert settings.searxng_port == 9999
    assert settings.searxng_base_url == "http://127.0.0.1:9999"


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


def test_backend_defaults_match_llama_cpp_first_starter_posture(monkeypatch, tmp_path):
    settings_module = _reload_settings(monkeypatch, tmp_path, None, None)

    settings = settings_module.load_settings()

    assert settings.use_local_model is True
    assert settings.llm_model_mode == "dev"
    assert settings.llm_model_policy == "auto"
    assert settings.use_ollama is False
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_model == "phi4-mini"
    assert settings.ollama_num_ctx == 8192
    assert settings.ollama_keep_alive == "5m"
    assert settings.use_searxng is False
    for name in RETIRED_SETTING_NAMES:
        assert name not in settings_module.SETTING_ENV_CLASSIFICATION


def test_external_llama_cpp_compatibility_settings_are_explicit(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "LLAMA_CPP_MANAGED=false\n"
        "LLAMA_CPP_BASE_URL=http://127.0.0.1:8888/v1\n"
        "LLAMA_CPP_MODEL_NAME=unsloth-model\n"
        "LLAMA_CPP_CONTEXT_SIZE=65536\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.llama_cpp_managed_explicit is True
    assert settings.llama_cpp_managed is False
    assert settings.llama_cpp_base_url_explicit is True
    assert settings.llama_cpp_base_url == "http://127.0.0.1:8888/v1"
    assert settings.llama_cpp_model_name == "unsloth-model"
    assert settings.llama_cpp_context_size == 65536


def test_blank_non_secret_env_values_do_not_mask_defaults(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "USE_LOCAL_MODEL=\nLLM_MODEL_MODE=\nLLM_MODEL_POLICY=\nOLLAMA_MODEL=\nOLLAMA_NUM_CTX=\nOLLAMA_KEEP_ALIVE=\nUSE_SEARXNG=\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.use_local_model is True
    assert settings.llm_model_mode == "dev"
    assert settings.llm_model_policy == "auto"
    assert settings.ollama_model == "phi4-mini"
    assert settings.ollama_num_ctx == 8192
    assert settings.ollama_keep_alive == "5m"
    assert settings.use_searxng is False


def test_llm_model_mode_accepts_prod(monkeypatch, tmp_path):
    settings_module = _reload_settings(monkeypatch, tmp_path, "LLM_MODEL_MODE=prod\n", None)

    settings = settings_module.load_settings()

    assert settings.llm_model_mode == "prod"


def test_llm_model_mode_rejects_invalid_value(monkeypatch, tmp_path):
    settings_module = _reload_settings(monkeypatch, tmp_path, "LLM_MODEL_MODE=staging\n", None)

    with pytest.raises(ValueError, match="LLM_MODEL_MODE"):
        settings_module.load_settings()


def test_resident_voice_segmenter_settings_read_from_env(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "\n".join(
            [
                "RESIDENT_VOICE_SPEECH_RMS_THRESHOLD=0.015",
                "RESIDENT_VOICE_NO_SPEECH_TIMEOUT_SECONDS=6",
                "RESIDENT_VOICE_SILENCE_END_SECONDS=0.75",
                "RESIDENT_VOICE_MAX_DURATION_SECONDS=9",
                "RESIDENT_VOICE_PRE_ROLL_SECONDS=0.5",
                "RESIDENT_VOICE_MIN_SPEECH_SECONDS=0.3",
            ]
        )
        + "\n",
        None,
    )

    settings = settings_module.load_settings()

    assert settings.resident_voice_speech_rms_threshold == 0.015
    assert settings.resident_voice_no_speech_timeout_seconds == 6.0
    assert settings.resident_voice_silence_end_seconds == 0.75
    assert settings.resident_voice_max_duration_seconds == 9.0
    assert settings.resident_voice_pre_roll_seconds == 0.5
    assert settings.resident_voice_min_speech_seconds == 0.3


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
    advertised_advanced = sorted(ENV_EXAMPLE_ADVANCED_NAMES & set(values))
    assert advertised_advanced == []
    advertised_external_llama_cpp = sorted(ENV_EXAMPLE_EXTERNAL_LLAMA_CPP_NAMES & set(values))
    assert advertised_external_llama_cpp == sorted(ENV_EXAMPLE_EXTERNAL_LLAMA_CPP_NAMES)
    assert "LLM_MODELS" not in values
    assert values["APP_NAME"] == "JARVISv7"
    assert values["JARVIS_LANGUAGE"] == "english"
    assert values["LLM_MODEL_MODE"] == "dev"
    assert values["LLM_MODEL_POLICY"] == "auto"
    assert values["LLM_MODEL_ID"] == ""
    assert values["OLLAMA_MODEL"] == "phi4-mini"
    assert (RETIRED_SETTING_NAMES - ENV_EXAMPLE_UNIMPLEMENTED_NAMES).isdisjoint(values)
    assert values["SEARXNG_PORT"] == "8910"
    assert values["JARVIS_SECRET_STORE_KEY"] == ""
    # Blank, not false: an explicit false routes a fresh install at an external llama.cpp
    # server nobody is running, so the shipped default could not serve a turn.
    assert values["LLAMA_CPP_MANAGED"] == ""
    assert values["USE_LOCAL_MODEL"].lower() in {"0", "1", "false", "true", "no", "yes", "off", "on"}
    assert values["USE_OLLAMA"].lower() in {"0", "1", "false", "true", "no", "yes", "off", "on"}
    assert values["USE_SEARXNG"].lower() in {"0", "1", "false", "true", "no", "yes", "off", "on"}
    assert values["USE_DDGS"].lower() in {"0", "1", "false", "true", "no", "yes", "off", "on"}
    assert values["USE_TAVILY"].lower() in {"0", "1", "false", "true", "no", "yes", "off", "on"}


def test_setting_env_classification_keeps_primary_starter_small():
    settings_module = importlib.import_module("backend.app.core.settings")
    classification = settings_module.SETTING_ENV_CLASSIFICATION

    for name in ENV_EXAMPLE_REQUIRED_NAMES:
        if name == "LLM_MODEL_ID":
            assert classification[name] == "advanced"
            continue
        assert classification[name] in {"primary", "services", "secret"}
    for name in ENV_EXAMPLE_ADVANCED_NAMES:
        assert classification[name] in {"advanced", "derived", "test-only"}
    for name in ENV_EXAMPLE_COMPATIBILITY_ALIAS_NAMES:
        assert classification[name] == "compatibility"
