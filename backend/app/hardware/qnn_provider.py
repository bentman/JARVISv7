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

        htp_backend_path = str(onnxruntime_qnn.get_qnn_htp_path())
        return {"backend_path": htp_backend_path}
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
    if provider_options is None:
        raise ImportError("onnxruntime-qnn package required for QNN provider")

    try:
        import onnxruntime_qnn
    except ImportError as exc:
        raise ImportError("onnxruntime-qnn package required for QNN provider") from exc

    # Register QNN provider library to enable device discovery
    plugin_library_path = str(onnxruntime_qnn.get_library_path())
    onnxruntime.register_execution_provider_library("QNNExecutionProvider", plugin_library_path)

    try:
        # Discover available QNN devices
        ep_devices = onnxruntime.get_ep_devices()
        qnn_devices = [d for d in ep_devices if getattr(d, "ep_name", None) == "QNNExecutionProvider"]
        qnn_device_details = [
            {
                "ep_name": getattr(d, "ep_name", None),
                "ep_vendor": getattr(d, "ep_vendor", None),
                "ep_metadata": getattr(d, "ep_metadata", None),
                "ep_options": getattr(d, "ep_options", None),
            }
            for d in qnn_devices
        ]
        last_error: Exception | None = None

        # Attempt preferred strategy: add_provider_for_devices
        if qnn_devices and hasattr(onnxruntime.SessionOptions, "add_provider_for_devices"):
            try:
                so = onnxruntime.SessionOptions()
                if disable_cpu_fallback:
                    so.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
                so.add_provider_for_devices(qnn_devices, provider_options)
                session = onnxruntime.InferenceSession(str(model_path), sess_options=so)
                return session, "add_provider_for_devices"
            except Exception as exc:
                last_error = exc

        # Fall back to provider list with backend_path
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
        except Exception as fallback_exc:
            raise RuntimeError(
                "QNN session creation failed for "
                f"model='{model_path}'; "
                f"plugin_library_path={plugin_library_path!r}; "
                f"provider_options={provider_options!r}; "
                f"qnn_device_details={qnn_device_details!r}; "
                f"add_provider_for_devices failure={last_error!r}; "
                f"provider_list_with_backend_path failure={fallback_exc!r}"
            ) from fallback_exc

    finally:
        # Unregister after session creation to keep global state clean
        try:
            onnxruntime.unregister_execution_provider_library("QNNExecutionProvider")
        except Exception:
            pass
