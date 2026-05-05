from __future__ import annotations

from pathlib import Path
from typing import Any

import onnxruntime


def get_qnn_provider_options() -> dict[str, str] | None:
    """Get QNN provider options including backend_path.

    Returns dict with 'backend_path' key if onnxruntime-qnn is available,
    otherwise returns None.

    Raises:
        ImportError: if onnxruntime_qnn module is not available.
    """
    try:
        import onnxruntime_qnn

        backend_path = str(onnxruntime_qnn.get_library_path())
        return {"backend_path": backend_path}
    except ImportError as exc:
        raise ImportError("onnxruntime-qnn package required for QNN provider") from exc


def create_qnn_session(
    model_path: str | Path,
    disable_cpu_fallback: bool = True,
) -> tuple[onnxruntime.InferenceSession, str]:
    """Create ONNX Runtime inference session with QNN execution provider.

    Attempts hybrid initialization strategy:
    1. Register QNN provider library and discover QNN devices
    2. Try SessionOptions.add_provider_for_devices() if devices available (preferred)
    3. Fall back to provider list with backend_path in provider_options

    Args:
        model_path: Path to ONNX model file.
        disable_cpu_fallback: If True, disable CPU fallback via session config.

    Returns:
        Tuple of (InferenceSession, initialization_method_string).
        Method string is either "add_provider_for_devices" or "provider_list_with_backend_path".

    Raises:
        RuntimeError: if QNN session creation fails completely.
        ImportError: if onnxruntime_qnn is not available.
    """
    model_path = Path(model_path)
    provider_options = get_qnn_provider_options()

    try:
        import onnxruntime_qnn
    except ImportError as exc:
        raise ImportError("onnxruntime-qnn package required for QNN provider") from exc

    # Register QNN provider library to enable device discovery
    backend_path = provider_options["backend_path"]
    onnxruntime.register_execution_provider_library("QNNExecutionProvider", backend_path)

    try:
        # Discover available QNN devices
        ep_devices = onnxruntime.get_ep_devices()
        qnn_devices = [d for d in ep_devices if getattr(d, "ep_name", None) == "QNNExecutionProvider"]

        # Attempt preferred strategy: add_provider_for_devices
        if qnn_devices and hasattr(onnxruntime.SessionOptions, "add_provider_for_devices"):
            try:
                so = onnxruntime.SessionOptions()
                if disable_cpu_fallback:
                    so.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
                so.add_provider_for_devices(qnn_devices, provider_options)
                session = onnxruntime.InferenceSession(str(model_path), sess_options=so)
                return session, "add_provider_for_devices"
            except Exception:
                pass

        # Fall back to provider list with backend_path
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

    finally:
        # Unregister after session creation to keep global state clean
        try:
            onnxruntime.unregister_execution_provider_library("QNNExecutionProvider")
        except Exception:
            pass
