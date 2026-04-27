from __future__ import annotations

import importlib
from pathlib import Path


ENV_NAMES = (
    "APP_NAME",
    "CONFIG_PATH",
    "DATA_PATH",
    "MODEL_PATH",
    "USE_LOCAL_MODEL",
    "LOCAL_MODEL_FETCH",
    "LLAMA_CPP_MODEL_PATH",
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
)

ENV_EXAMPLE_REQUIRED_NAMES: set[str] = {
    "APP_NAME",
    "CONFIG_PATH",
    "DATA_PATH",
    "MODEL_PATH",
    "USE_LOCAL_MODEL",
    "LOCAL_MODEL_FETCH",
    "LLAMA_CPP_MODEL_PATH",
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


def test_settings_prefer_shell_env_over_env_files(monkeypatch, tmp_path):
    settings_module = _reload_settings(
        monkeypatch,
        tmp_path,
        "OLLAMA_BASE_URL=http://env-file:11434\nOLLAMA_MODEL=env-file-model\nOLLAMA_NUM_CTX=2048\nJARVISV7_LIVE_TESTS=false\n",
        "OLLAMA_BASE_URL=http://example-file:11434\nOLLAMA_MODEL=example-model\nOLLAMA_NUM_CTX=1024\nJARVISV7_LIVE_TESTS=false\n",
    )
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://shell:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "shell-model")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "8192")
    monkeypatch.setenv("JARVISV7_LIVE_TESTS", "true")

    settings = settings_module.load_settings()

    assert settings.ollama_base_url == "http://shell:11434"
    assert settings.ollama_model == "shell-model"
    assert settings.ollama_num_ctx == 8192
    assert settings.live_tests is True


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
    assert values["OLLAMA_MODEL"]
    assert values["OLLAMA_NUM_CTX"]
    assert values["JARVISV7_LIVE_TESTS"].lower() in {"0", "1", "false", "true", "no", "yes", "off", "on"}
    assert values["LOCAL_MODEL_FETCH"].lower() in {"0", "1", "false", "true", "no", "yes", "off", "on"}
    assert values["PICOVOICE_ACCESS_KEY"] in {"", "<placeholder>", "<secret>"}