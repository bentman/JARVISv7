from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import ModuleType

import onnxruntime


def _candidate_qnn_htp_paths() -> list[Path]:
    candidates: list[Path] = []

    for module in (onnxruntime, _optional_onnxruntime_qnn_module()):
        if module is None:
            continue
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
