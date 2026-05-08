from __future__ import annotations

from pathlib import Path

import onnxruntime
import pytest

from backend.app.hardware.qnn_provider import create_qnn_session
from backend.app.models.catalog import get_model_entry
from backend.tests.conftest import SKIP_UNLESS_ARM64, SKIP_UNLESS_LIVE, SKIP_UNLESS_QNN


def _find_required_model_file(root: Path, filename: str) -> Path:
    candidates = sorted(path for path in root.rglob(filename) if path.is_file())
    if not candidates:
        raise FileNotFoundError(f"missing required model file '{filename}' under {root}")
    return candidates[0]


def _summarize_onnx_model(path: Path) -> dict[str, object]:
    import onnx

    model = onnx.load(str(path))
    op_types = sorted({node.op_type for node in model.graph.node})
    epcontext_present = any(node.op_type == "EPContext" for node in model.graph.node)
    return {
        "path": str(path),
        "node_count": len(model.graph.node),
        "op_type_count": len(op_types),
        "op_types_sample": op_types[:25],
        "epcontext_present": epcontext_present,
    }


def _normalize_attribute_value(value: object) -> object:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore")
        except Exception:
            return repr(value)
    if isinstance(value, list):
        return [_normalize_attribute_value(item) for item in value]
    return value


def _collect_epcontext_diagnostics(onnx_path: Path, artifact_root: Path) -> dict[str, object]:
    import onnx

    model = onnx.load(str(onnx_path))
    ep_nodes = [node for node in model.graph.node if node.op_type == "EPContext"]

    node_diagnostics: list[dict[str, object]] = []
    referenced_candidates: list[str] = []

    for node in ep_nodes:
        attrs: dict[str, object] = {}
        for attr in node.attribute:
            raw = onnx.helper.get_attribute_value(attr)
            normalized = _normalize_attribute_value(raw)
            attrs[attr.name] = normalized

            candidates: list[str] = []
            if isinstance(normalized, str):
                candidates = [normalized]
            elif isinstance(normalized, list):
                candidates = [item for item in normalized if isinstance(item, str)]

            for candidate in candidates:
                lowered = candidate.lower()
                if ".bin" in lowered or "context" in lowered:
                    referenced_candidates.append(candidate)

        node_diagnostics.append(
            {
                "name": node.name,
                "attribute_count": len(node.attribute),
                "attributes": attrs,
            }
        )

    unique_refs = sorted(set(referenced_candidates))
    resolved_refs: list[dict[str, object]] = []
    for ref in unique_refs:
        onnx_dir_path = (onnx_path.parent / ref).resolve()
        artifact_root_path = (artifact_root / ref).resolve()
        resolved_refs.append(
            {
                "reference": ref,
                "onnx_dir_candidate": str(onnx_dir_path),
                "onnx_dir_exists": onnx_dir_path.is_file(),
                "artifact_root_candidate": str(artifact_root_path),
                "artifact_root_exists": artifact_root_path.is_file(),
            }
        )

    adjacent_bins = sorted(str(path) for path in onnx_path.parent.glob("*.bin"))
    return {
        "onnx_path": str(onnx_path),
        "adjacent_bin_files": adjacent_bins,
        "epcontext_node_count": len(ep_nodes),
        "epcontext_nodes": node_diagnostics,
        "referenced_sidecars": resolved_refs,
    }


@pytest.mark.live
@pytest.mark.arm64
@pytest.mark.qnn
@pytest.mark.stt
@pytest.mark.requires_qairt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_ARM64, reason="requires ARM64 host")
@pytest.mark.skipif(SKIP_UNLESS_QNN, reason="requires QNN execution provider readiness")
def test_qnn_dll_discoverable_via_qairt_sdk_path() -> None:
    import onnxruntime_qnn

    backend_path = Path(onnxruntime_qnn.get_library_path())
    htp_path = Path(onnxruntime_qnn.get_qnn_htp_path())

    assert backend_path.is_file(), f"QNN plugin library not found at {backend_path}"
    assert htp_path.is_file(), f"QNN HTP backend not found at {htp_path}"


@pytest.mark.live
@pytest.mark.arm64
@pytest.mark.qnn
@pytest.mark.stt
@pytest.mark.requires_qairt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_ARM64, reason="requires ARM64 host")
@pytest.mark.skipif(SKIP_UNLESS_QNN, reason="requires QNN execution provider readiness")
def test_qnn_ep_registers_in_onnxruntime() -> None:
    import onnxruntime_qnn

    backend_path = str(onnxruntime_qnn.get_library_path())
    onnxruntime.register_execution_provider_library("QNNExecutionProvider", backend_path)
    try:
        ep_devices = list(onnxruntime.get_ep_devices())
        assert any(device.ep_name == "QNNExecutionProvider" for device in ep_devices)
    finally:
        try:
            onnxruntime.unregister_execution_provider_library("QNNExecutionProvider")
        except Exception:
            pass


@pytest.mark.live
@pytest.mark.arm64
@pytest.mark.qnn
@pytest.mark.stt
@pytest.mark.requires_qairt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_ARM64, reason="requires ARM64 host")
@pytest.mark.skipif(SKIP_UNLESS_QNN, reason="requires QNN execution provider readiness")
def test_qnn_compatible_whisper_artifact_loads_with_qnn_ep() -> None:
    import onnxruntime_qnn

    entry = get_model_entry("stt", "whisper-tiny-qnn-precompiled-snapdragon-x-elite")
    model_root = entry.local_path

    encoder_path = _find_required_model_file(model_root, "encoder.onnx")
    decoder_path = _find_required_model_file(model_root, "decoder.onnx")
    bin_sidecars = sorted(str(path) for path in model_root.rglob("*.bin"))

    plugin_library_path = str(onnxruntime_qnn.get_library_path())
    htp_backend_path = str(onnxruntime_qnn.get_qnn_htp_path())
    provider_options = {"backend_path": htp_backend_path}

    onnxruntime.register_execution_provider_library("QNNExecutionProvider", plugin_library_path)
    try:
        ep_devices = list(onnxruntime.get_ep_devices())
        qnn_devices = [d for d in ep_devices if getattr(d, "ep_name", None) == "QNNExecutionProvider"]
        assert qnn_devices, "QNNExecutionProvider device list is empty"

        print("ort_version:", onnxruntime.__version__)
        print("plugin_library_path:", plugin_library_path)
        print("htp_backend_path:", htp_backend_path)
        print("provider_options:", provider_options)
        print("encoder_path:", encoder_path)
        print("decoder_path:", decoder_path)
        print("bin_sidecars:", bin_sidecars)
        print("encoder_onnx_summary:", _summarize_onnx_model(encoder_path))
        print("decoder_onnx_summary:", _summarize_onnx_model(decoder_path))
        print("encoder_epcontext_diagnostics:", _collect_epcontext_diagnostics(encoder_path, model_root))
        print("decoder_epcontext_diagnostics:", _collect_epcontext_diagnostics(decoder_path, model_root))
        print(
            "qnn_device_details:",
            [
                {
                    "ep_name": getattr(device, "ep_name", None),
                    "ep_vendor": getattr(device, "ep_vendor", None),
                    "ep_metadata": getattr(device, "ep_metadata", None),
                    "ep_options": getattr(device, "ep_options", None),
                }
                for device in qnn_devices
            ],
        )

        so_encoder = onnxruntime.SessionOptions()
        so_encoder.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        so_encoder.add_provider_for_devices(qnn_devices, provider_options)
        encoder_session = onnxruntime.InferenceSession(str(encoder_path), sess_options=so_encoder)

        so_decoder = onnxruntime.SessionOptions()
        so_decoder.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        so_decoder.add_provider_for_devices(qnn_devices, provider_options)
        decoder_session = onnxruntime.InferenceSession(str(decoder_path), sess_options=so_decoder)

        direct_encoder_providers = encoder_session.get_providers()
        direct_decoder_providers = decoder_session.get_providers()
        print("direct_encoder_providers:", direct_encoder_providers)
        print("direct_decoder_providers:", direct_decoder_providers)

        # Isolate helper-path diagnostics from direct-path provider registration state.
        onnxruntime.unregister_execution_provider_library("QNNExecutionProvider")

        for model_kind, model_path in (("encoder", encoder_path), ("decoder", decoder_path)):
            try:
                helper_session, helper_method = create_qnn_session(
                    model_path, disable_cpu_fallback=True
                )
                print(f"helper_{model_kind}_method:", helper_method)
                print(f"helper_{model_kind}_providers:", helper_session.get_providers())
            except Exception as exc:
                print(f"helper_{model_kind}_exception:", repr(exc))

        assert direct_encoder_providers[0] == "QNNExecutionProvider", (
            f"expected QNN as primary provider, got {direct_encoder_providers}"
        )
        assert direct_decoder_providers[0] == "QNNExecutionProvider", (
            f"expected QNN as primary provider, got {direct_decoder_providers}"
        )
    finally:
        try:
            onnxruntime.unregister_execution_provider_library("QNNExecutionProvider")
        except Exception:
            pass
