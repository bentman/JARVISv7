from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import onnxruntime


@dataclass(frozen=True)
class QnnProviderActivationResult:
    provider_registered: bool
    provider_library_path: Path | None = None
    dll_directory_path: Path | None = None
    error: str | None = None


_DLL_DIRECTORY_HANDLES: list[object] = []
_ACTIVATION_RESULT: QnnProviderActivationResult | None = None


def _candidate_qnn_htp_paths() -> list[Path]:
    candidates: list[Path] = []

    for module in (onnxruntime, _optional_onnxruntime_qnn_module()):
        if module is None:
            continue
        htp_path = _qnn_htp_path_from_helper(module)
        if htp_path is not None:
            candidates.append(htp_path)
        module_file = getattr(module, "__file__", None)
        if module_file:
            module_root = Path(module_file).resolve().parent
            candidates.extend(path for path in module_root.rglob("QnnHtp.dll") if path.is_file())

    qairt_sdk_path = os.getenv("QAIRT_SDK_PATH")
    if qairt_sdk_path:
        qairt_root = Path(qairt_sdk_path)
        for root in (qairt_root, qairt_root / "bin", qairt_root / "lib"):
            candidate = root / "QnnHtp.dll"
            if candidate.is_file():
                candidates.append(candidate)

    return candidates


def _optional_onnxruntime_qnn_module() -> ModuleType | None:
    try:
        return importlib.import_module("onnxruntime_qnn")
    except Exception:
        return None


def _qnn_package_root(module: ModuleType) -> Path | None:
    lib_dir = getattr(module, "LIB_DIR_FULL_PATH", None)
    if lib_dir:
        return Path(lib_dir).resolve()
    module_file = getattr(module, "__file__", None)
    if module_file:
        return Path(module_file).resolve().parent
    return None


def _qnn_provider_library_path(module: ModuleType) -> Path | None:
    get_library_path = getattr(module, "get_library_path", None)
    if callable(get_library_path):
        candidate = Path(get_library_path()).resolve()
        if candidate.is_file():
            return candidate

    root = _qnn_package_root(module)
    if root is None:
        return None
    candidate = root / "onnxruntime_providers_qnn.dll"
    return candidate if candidate.is_file() else None


def _qnn_htp_path_from_helper(module: ModuleType) -> Path | None:
    get_qnn_htp_path = getattr(module, "get_qnn_htp_path", None)
    if not callable(get_qnn_htp_path):
        return None
    candidate = Path(get_qnn_htp_path()).resolve()
    return candidate if candidate.is_file() else None


def _available_providers() -> list[str]:
    return list(onnxruntime.get_available_providers())


def activate_qnn_execution_provider() -> QnnProviderActivationResult:
    global _ACTIVATION_RESULT

    if "QNNExecutionProvider" in _available_providers():
        _ACTIVATION_RESULT = QnnProviderActivationResult(provider_registered=True)
        return _ACTIVATION_RESULT

    qnn_module = _optional_onnxruntime_qnn_module()
    if qnn_module is None:
        return QnnProviderActivationResult(
            provider_registered=False,
            error="onnxruntime_qnn import failed",
        )

    provider_library_path = _qnn_provider_library_path(qnn_module)
    if provider_library_path is None:
        return QnnProviderActivationResult(
            provider_registered=False,
            error="onnxruntime_qnn provider library not found",
        )

    dll_directory_path = _qnn_package_root(qnn_module)
    if dll_directory_path is not None:
        dll_api = getattr(os, "add_dll_directory", None)
        if dll_api is not None:
            try:
                _DLL_DIRECTORY_HANDLES.append(dll_api(str(dll_directory_path)))
            except Exception as exc:
                return QnnProviderActivationResult(
                    provider_registered=False,
                    provider_library_path=provider_library_path,
                    dll_directory_path=dll_directory_path,
                    error=f"add_dll_directory failed: {exc}",
                )

    register_provider = getattr(onnxruntime, "register_execution_provider_library", None)
    if not callable(register_provider):
        return QnnProviderActivationResult(
            provider_registered=False,
            provider_library_path=provider_library_path,
            dll_directory_path=dll_directory_path,
            error="onnxruntime register_execution_provider_library unavailable",
        )

    try:
        register_provider("QNNExecutionProvider", str(provider_library_path))
    except Exception as exc:
        return QnnProviderActivationResult(
            provider_registered=False,
            provider_library_path=provider_library_path,
            dll_directory_path=dll_directory_path,
            error=f"QNNExecutionProvider registration failed: {exc}",
        )

    provider_registered = "QNNExecutionProvider" in _available_providers()
    result = QnnProviderActivationResult(
        provider_registered=provider_registered,
        provider_library_path=provider_library_path,
        dll_directory_path=dll_directory_path,
        error=None if provider_registered else "QNNExecutionProvider not exposed after registration",
    )
    if provider_registered:
        _ACTIVATION_RESULT = result
    return result


def resolve_qnn_htp_backend_path() -> Path:
    backend_path = next(iter(_candidate_qnn_htp_paths()), None)
    if backend_path is None:
        raise FileNotFoundError(
            "QnnHtp.dll not found in installed onnxruntime package files or QAIRT_SDK_PATH"
        )
    return backend_path


def get_qnn_provider_options() -> dict[str, str] | None:
    """Get QNN provider options for the built-in ONNX Runtime QNN provider."""
    return {"backend_path": str(resolve_qnn_htp_backend_path())}


def create_qnn_session(
    model_path: str | Path,
    disable_cpu_fallback: bool = True,
) -> tuple[onnxruntime.InferenceSession, str]:
    """Create ONNX Runtime inference session with QNN execution provider.

    Args:
        model_path: Path to ONNX model file.
        disable_cpu_fallback: If True, disable CPU fallback via session config.

    Returns:
        Tuple of (InferenceSession, initialization_method_string).
        Method string is "provider_list_with_backend_path".

    Raises:
        RuntimeError: if QNN session creation fails.
    """
    model_path = Path(model_path)
    activation = activate_qnn_execution_provider()
    if not activation.provider_registered:
        raise RuntimeError(f"QNNExecutionProvider activation failed: {activation.error}")
    provider_options = get_qnn_provider_options()

    try:
        so = onnxruntime.SessionOptions()
        if disable_cpu_fallback:
            so.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        session = onnxruntime.InferenceSession(
            str(model_path),
            sess_options=so,
            providers=["QNNExecutionProvider"],
            provider_options=[provider_options],
        )
        return session, "provider_list_with_backend_path"
    except Exception as exc:
        raise RuntimeError(
            "QNN session creation failed for "
            f"model='{model_path}'; "
            f"provider_options={provider_options!r}; "
            f"provider_list_with_backend_path failure={exc!r}"
        ) from exc
