from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware import preflight


def _make_profile(**overrides) -> HardwareProfile:
    return HardwareProfile(**overrides)


def _make_module(*providers: str):
    return SimpleNamespace(get_available_providers=lambda: list(providers))


def test_preflight_emits_import_token_for_installed_package(monkeypatch) -> None:
    preflight._CACHE.clear()

    def fake_import(name: str):
        if name == "pytest":
            return SimpleNamespace(__name__=name)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(preflight.importlib, "import_module", fake_import)
    monkeypatch.setattr(preflight, "_bootstrap_windows_dlls", lambda profile, tokens, log: None)

    result = preflight.run_preflight(_make_profile(os_name="linux"), ["dev"])

    assert "import:pytest" in result.tokens


def test_preflight_emits_missing_token_for_uninstalled_package(monkeypatch) -> None:
    preflight._CACHE.clear()

    def fake_import(name: str):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(preflight.importlib, "import_module", fake_import)
    monkeypatch.setattr(preflight, "_bootstrap_windows_dlls", lambda profile, tokens, log: None)

    result = preflight.run_preflight(_make_profile(os_name="linux"), ["dev"])

    assert "import:pytest:MISSING" in result.tokens
    assert "pytest" in result.probe_errors


def test_preflight_is_idempotent_in_same_process(monkeypatch) -> None:
    preflight._CACHE.clear()
    calls = {"bootstrap": 0, "imports": 0}

    def fake_bootstrap(profile, tokens, log):
        calls["bootstrap"] += 1

    def fake_imports(installed_extras, tokens, probe_errors):
        calls["imports"] += 1
        tokens.append("import:pytest")

    monkeypatch.setattr(preflight, "_bootstrap_windows_dlls", fake_bootstrap)
    monkeypatch.setattr(preflight, "_probe_imports", fake_imports)
    monkeypatch.setattr(preflight, "_probe_execution_providers", lambda tokens, errors: None)

    first = preflight.run_preflight(_make_profile(os_name="linux"), ["dev"])
    second = preflight.run_preflight(_make_profile(os_name="linux"), ["dev"])

    assert first.tokens == second.tokens
    assert calls == {"bootstrap": 1, "imports": 1}


def test_preflight_dll_bootstrap_survives_windows_missing_dll_without_raising(monkeypatch) -> None:
    preflight._CACHE.clear()
    monkeypatch.setattr(
        preflight,
        "_candidate_dll_roots",
        lambda profile: [("cuda", Path("C:/missing-sdk"))],
    )
    monkeypatch.setattr(
        preflight.importlib,
        "import_module",
        lambda name: SimpleNamespace(__name__=name),
    )

    result = preflight.run_preflight(
        _make_profile(
            os_name="windows",
            arch="amd64",
            gpu_available=True,
            gpu_vendor="nvidia",
            cuda_available=True,
        ),
        ["hw-cpu-base"],
    )

    assert any(entry.startswith("cuda:missing:") for entry in result.dll_discovery_log)


def test_preflight_ep_probe_emits_ep_tokens_when_onnxruntime_available(monkeypatch) -> None:
    preflight._CACHE.clear()

    def fake_import(name: str):
        modules = {
            "onnxruntime": _make_module("CUDAExecutionProvider", "DmlExecutionProvider"),
            "onnx_asr": SimpleNamespace(__name__=name),
            "kokoro_onnx": SimpleNamespace(__name__=name),
            "openwakeword": SimpleNamespace(__name__=name),
        }
        if name in modules:
            return modules[name]
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(preflight.importlib, "import_module", fake_import)
    monkeypatch.setattr(preflight, "_bootstrap_windows_dlls", lambda profile, tokens, log: None)

    result = preflight.run_preflight(_make_profile(os_name="linux"), ["hw-x64-base"])

    assert "import:onnxruntime" in result.tokens
    assert "ep:CUDAExecutionProvider" in result.tokens
    assert "ep:DmlExecutionProvider" in result.tokens


def test_preflight_ep_probe_skipped_when_onnxruntime_not_imported(monkeypatch) -> None:
    preflight._CACHE.clear()
    calls: list[str] = []

    def fake_import(name: str):
        calls.append(name)
        if name == "onnxruntime":
            raise AssertionError("onnxruntime should not be probed without the import token")
        if name in {"pytest", "pytest_cov", "pytest_asyncio", "ruff", "mypy", "pre_commit"}:
            return SimpleNamespace(__name__=name)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(preflight.importlib, "import_module", fake_import)
    monkeypatch.setattr(preflight, "_bootstrap_windows_dlls", lambda profile, tokens, log: None)

    result = preflight.run_preflight(_make_profile(os_name="linux"), ["dev"])

    assert "onnxruntime" not in calls
    assert "ep:CUDAExecutionProvider" not in result.tokens
