from __future__ import annotations

from copy import deepcopy

import pytest

from backend.app.core.capabilities import HardwareProfile
from backend.app.core.settings import Settings
from backend.app.models.catalog import load_catalog
from backend.app.models.llm_selection import LLMSelectionError, select_llm_model


def _settings(policy: str | None = None, model_id: str | None = None) -> Settings:
    return Settings(llm_model_policy=policy, llm_model_id=model_id)


def _catalog() -> dict:
    return deepcopy(load_catalog("llm"))


def test_auto_policy_maps_cuda_host_to_balanced_dev_alias() -> None:
    selection = select_llm_model(
        "voice_chat",
        HardwareProfile(
            os_name="windows",
            arch="amd64",
            gpu_vendor="nvidia",
            gpu_available=True,
            cuda_available=True,
        ),
        settings=_settings(),
    )

    assert selection.model_id == "assistant-small-q4"
    assert selection.policy == "auto"
    assert selection.role == "balanced"
    assert selection.role_status == "dev-alias"
    assert selection.hardware_selector == "windows_amd64_gpu_nvidia_cuda"
    assert "role balanced" in selection.reason


def test_named_policy_uses_wildcard_role() -> None:
    selection = select_llm_model(
        "text_chat",
        HardwareProfile(os_name="windows", arch="amd64"),
        settings=_settings(policy="quality"),
    )

    assert selection.model_id == "assistant-small-q4"
    assert selection.policy == "quality"
    assert selection.role == "quality"
    assert selection.hardware_selector == "*"


def test_explicit_model_override_wins_over_policy() -> None:
    selection = select_llm_model(
        "voice_chat",
        HardwareProfile(os_name="windows", arch="amd64"),
        settings=_settings(policy="quality", model_id="assistant-small-q4"),
    )

    assert selection.model_id == "assistant-small-q4"
    assert selection.role == "override"
    assert selection.override is True
    assert "LLM_MODEL_ID override" in selection.reason


def test_invalid_policy_fails_closed() -> None:
    with pytest.raises(LLMSelectionError, match="policy 'missing'"):
        select_llm_model(
            "voice_chat",
            HardwareProfile(os_name="windows", arch="amd64"),
            settings=_settings(policy="missing"),
        )


def test_invalid_role_fails_closed() -> None:
    catalog = _catalog()
    catalog["llm_selection"]["policies"]["auto"]["windows_amd64_cpu"] = "missing-role"

    with pytest.raises(LLMSelectionError, match="role 'missing-role'"):
        select_llm_model(
            "voice_chat",
            HardwareProfile(os_name="windows", arch="amd64"),
            settings=_settings(),
            catalog=catalog,
        )


def test_invalid_role_model_fails_closed() -> None:
    catalog = _catalog()
    catalog["llm_selection"]["roles"]["portable"]["model"] = "missing-model"

    with pytest.raises(LLMSelectionError, match="missing-model"):
        select_llm_model(
            "voice_chat",
            HardwareProfile(os_name="windows", arch="amd64"),
            settings=_settings(policy="portable"),
            catalog=catalog,
        )


def test_route_compatibility_is_required() -> None:
    with pytest.raises(LLMSelectionError, match="route 'image_chat'"):
        select_llm_model(
            "image_chat",
            HardwareProfile(os_name="windows", arch="amd64"),
            settings=_settings(policy="portable"),
        )


def test_arm64_qualcomm_qnn_host_still_selects_existing_model() -> None:
    selection = select_llm_model(
        "voice_chat",
        HardwareProfile(
            os_name="windows",
            arch="arm64",
            npu_vendor="qualcomm",
            npu_available=True,
        ),
        settings=_settings(),
    )

    assert selection.model_id == "assistant-small-q4"
    assert selection.role == "portable"
    assert selection.hardware_selector == "windows_arm64_npu_qualcomm_qnn"
