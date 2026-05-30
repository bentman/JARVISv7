from __future__ import annotations

from pathlib import Path

import onnxruntime
import pytest

from backend.app.hardware.qnn_provider import create_qnn_session, get_qnn_provider_options
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
    provider_options = get_qnn_provider_options()
    htp_path = Path(provider_options["backend_path"])

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
    providers = onnxruntime.get_available_providers()

    assert "QNNExecutionProvider" in providers



