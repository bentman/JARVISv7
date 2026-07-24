from __future__ import annotations

from copy import deepcopy

import pytest

from backend.app.core.capabilities import HardwareProfile
from backend.app.core.settings import Settings
from backend.app.models.catalog import load_catalog
from backend.app.models.llm_selection import LLMSelectionError, select_llm_model


def _settings(
    policy: str | None = None,
    model_id: str | None = None,
    mode: str = "dev",
) -> Settings:
    return Settings(llm_model_mode=mode, llm_model_policy=policy, llm_model_id=model_id)


def _catalog() -> dict:
    return deepcopy(load_catalog("llm"))


def test_dev_mode_selects_development_model_even_on_cuda_host() -> None:
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

    assert selection.model_id == "assistant-qwen3-4b-q4-portable"
    assert selection.mode == "dev"
    assert selection.policy == "auto"
    assert selection.role == "dev"
    assert selection.role_status == "active-development-behavioral-default"
    assert selection.hardware_selector == "mode:dev"
    assert "mode dev selected assistant-qwen3-4b-q4-portable" in selection.reason


def test_prod_auto_policy_maps_cuda_host_to_balanced_model() -> None:
    selection = select_llm_model(
        "voice_chat",
        HardwareProfile(
            os_name="windows",
            arch="amd64",
            gpu_vendor="nvidia",
            gpu_available=True,
            cuda_available=True,
        ),
        settings=_settings(mode="prod"),
    )

    assert selection.model_id == "assistant-qwen3-8b-q5-balanced"
    assert selection.mode == "prod"
    assert selection.policy == "auto"
    assert selection.role == "balanced"
    assert selection.role_status == "active"
    assert selection.hardware_selector == "windows_amd64_gpu_nvidia_cuda"
    assert "role balanced" in selection.reason


def test_prod_auto_policy_maps_linux_cuda_host_to_balanced_model() -> None:
    selection = select_llm_model(
        "voice_chat",
        HardwareProfile(
            os_name="linux",
            arch="amd64",
            gpu_vendor="nvidia",
            gpu_available=True,
            cuda_available=True,
        ),
        settings=_settings(mode="prod"),
    )

    assert selection.model_id == "assistant-qwen3-8b-q5-balanced"
    assert selection.hardware_selector == "linux_amd64_gpu_nvidia_cuda"


def test_prod_auto_policy_maps_linux_cpu_host_to_portable_model() -> None:
    selection = select_llm_model(
        "voice_chat",
        HardwareProfile(os_name="linux", arch="amd64"),
        settings=_settings(mode="prod"),
    )

    assert selection.model_id == "assistant-qwen3-4b-q4-portable"
    assert selection.hardware_selector == "linux_amd64_cpu"


def test_prod_auto_policy_maps_cpu_host_to_portable_model() -> None:
    selection = select_llm_model(
        "voice_chat",
        HardwareProfile(os_name="windows", arch="amd64"),
        settings=_settings(mode="prod"),
    )

    assert selection.model_id == "assistant-qwen3-4b-q4-portable"
    assert selection.mode == "prod"
    assert selection.policy == "auto"
    assert selection.role == "portable"
    assert selection.hardware_selector == "windows_amd64_cpu"


def test_prod_named_policy_degrades_to_portable_on_cpu() -> None:
    selection = select_llm_model(
        "text_chat",
        HardwareProfile(os_name="windows", arch="amd64"),
        settings=_settings(policy="quality", mode="prod"),
    )

    assert selection.model_id == "assistant-qwen3-4b-q4-portable"
    assert selection.mode == "prod"
    assert selection.policy == "quality"
    assert selection.role == "portable"
    assert selection.hardware_selector == "*"


def test_explicit_model_override_wins_over_policy() -> None:
    selection = select_llm_model(
        "voice_chat",
        HardwareProfile(os_name="windows", arch="amd64"),
        settings=_settings(policy="quality", model_id="assistant-small-q4", mode="prod"),
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
            settings=_settings(policy="missing", mode="prod"),
        )


def test_invalid_role_fails_closed() -> None:
    catalog = _catalog()
    catalog["llm_selection"]["policies"]["auto"]["windows_amd64_cpu"] = "missing-role"

    with pytest.raises(LLMSelectionError, match="role 'missing-role'"):
        select_llm_model(
            "voice_chat",
            HardwareProfile(os_name="windows", arch="amd64"),
            settings=_settings(mode="prod"),
            catalog=catalog,
        )


def test_invalid_role_model_fails_closed() -> None:
    catalog = _catalog()
    catalog["llm_selection"]["roles"]["portable"]["model"] = "missing-model"

    with pytest.raises(LLMSelectionError, match="missing-model"):
        select_llm_model(
            "voice_chat",
            HardwareProfile(os_name="windows", arch="amd64"),
            settings=_settings(policy="portable", mode="prod"),
            catalog=catalog,
        )


def test_route_compatibility_is_required() -> None:
    with pytest.raises(LLMSelectionError, match="route 'image_chat'"):
        select_llm_model(
            "image_chat",
            HardwareProfile(os_name="windows", arch="amd64"),
            settings=_settings(policy="portable", mode="prod"),
        )


def test_prod_arm64_qualcomm_qnn_host_selects_portable_model() -> None:
    selection = select_llm_model(
        "voice_chat",
        HardwareProfile(
            os_name="windows",
            arch="arm64",
            npu_vendor="qualcomm",
            npu_available=True,
        ),
        settings=_settings(mode="prod"),
    )

    assert selection.model_id == "assistant-qwen3-4b-q4-portable"
    assert selection.mode == "prod"
    assert selection.role == "portable"
    assert selection.hardware_selector == "windows_arm64_npu_qualcomm_qnn"


def test_prod_policies_select_only_qwen3_role_models() -> None:
    profile = HardwareProfile(os_name="windows", arch="amd64")
    for policy in ["auto", "portable", "balanced", "quality", "diagnostic"]:
        selection = select_llm_model("voice_chat", profile, settings=_settings(policy=policy, mode="prod"))
        assert selection.model_id != "assistant-small-q4"
        assert selection.model_id.startswith("assistant-qwen3-")


def test_catalog_encodes_family_sampling_and_host_tier_policy() -> None:
    catalog = _catalog()
    models = catalog["models"]

    assert models["assistant-small-q4"]["generation_defaults"] == {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.1,
        "max_tokens": 256,
        "stop": ["\nUser:", "\nAssistant:", "User:", "Assistant:"],
    }

    expected_quants = {
        "assistant-qwen3-0p6b-q8-diagnostic": "q8_0",
        "assistant-qwen3-4b-q4-portable": "q4_k_m",
        "assistant-qwen3-8b-q5-balanced": "q5_k_m",
        "assistant-qwen3-14b-q4-quality": "q4_k_m",
    }
    expected_contexts = {
        "linux_amd64_cpu": 4096,
        "linux_amd64_gpu_nvidia_cuda": 8192,
        "windows_amd64_cpu": 4096,
        "windows_arm64_cpu": 4096,
        "windows_amd64_gpu_nvidia_cuda": 8192,
        "windows_amd64_gpu_amd": 4096,
        "windows_amd64_gpu_intel": 4096,
        "windows_arm64_npu_qualcomm_base": 2048,
        "windows_arm64_gpu_qualcomm_adreno_opencl": 4096,
        "windows_arm64_npu_qualcomm_qnn": 4096,
    }
    for model_id, quantization in expected_quants.items():
        model = models[model_id]
        assert model["quantization"] == quantization
        assert model["generation_defaults"] == {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "repeat_penalty": 1.0,
            "max_tokens": 256,
            "chat_template_kwargs": {"enable_thinking": False},
            "stop": ["\nUser:", "\nAssistant:", "User:", "Assistant:"],
        }
        profiles = model["serve_profiles"]["hardware_profiles"]
        assert {
            profile_id: profile["launch"]["ctx_size"]
            for profile_id, profile in profiles.items()
        } == expected_contexts
