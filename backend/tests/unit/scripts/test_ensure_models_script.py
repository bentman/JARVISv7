from __future__ import annotations

import io
import zipfile
from pathlib import Path

from backend.app.core.capabilities import HardwareProfile
from scripts import ensure_models


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.content = payload

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str) -> _FakeResponse:
        return _FakeResponse(self._payload)


def test_verify_entry_url_zip_checks_required_files_and_extensions(tmp_path: Path) -> None:
    model_root = tmp_path / "models" / "stt" / "qualcomm-whisper"
    (model_root / "artifact").mkdir(parents=True)
    (model_root / "artifact" / "encoder_model.onnx").write_bytes(b"onnx")
    (model_root / "artifact" / "decoder_model_merged.onnx").write_bytes(b"onnx")
    (model_root / "artifact" / "weights.bin").write_bytes(b"bin")

    entry = ensure_models.ModelEntry(
        family="stt",
        name="qualcomm-whisper-test",
        config={
            "local_path": str(model_root),
            "source": {
                "type": "url_zip",
                "url": "https://example.invalid/model.zip",
                "required_files_anywhere": ["encoder_model.onnx", "decoder_model_merged.onnx"],
                "required_extensions_anywhere": [".onnx", ".bin"],
            },
        },
    )

    result = ensure_models._verify_entry(entry)

    assert result["ready"] is True
    assert result["missing"] == []
    assert any(path.endswith("encoder_model.onnx") for path in result["present"])
    assert any(path.endswith("weights.bin") for path in result["present"])


def test_download_url_zip_preserves_relative_layout(tmp_path: Path, monkeypatch) -> None:
    payload = _zip_bytes(
        {
            "models/encoder_model.onnx": b"enc",
            "models/decoder_model_merged.onnx": b"dec",
            "models/assets/weights.bin": b"bin",
        }
    )

    monkeypatch.setattr(ensure_models.httpx, "Client", lambda **kwargs: _FakeClient(payload))

    model_root = tmp_path / "models" / "stt" / "qualcomm-whisper"
    entry = ensure_models.ModelEntry(
        family="stt",
        name="qualcomm-whisper-test",
        config={
            "local_path": str(model_root),
            "source": {
                "type": "url_zip",
                "url": "https://example.invalid/model.zip",
                "required_files_anywhere": ["encoder_model.onnx", "decoder_model_merged.onnx"],
                "required_extensions_anywhere": [".onnx", ".bin"],
            },
        },
    )

    acquired = ensure_models._download_url_zip(entry, dry_run=False)

    assert "models/encoder_model.onnx" in acquired
    assert "models/decoder_model_merged.onnx" in acquired
    assert "models/assets/weights.bin" in acquired
    assert (model_root / "models" / "encoder_model.onnx").is_file()
    assert (model_root / "models" / "decoder_model_merged.onnx").is_file()
    assert (model_root / "models" / "assets" / "weights.bin").is_file()


def test_verify_llm_single_file_artifact_reports_present_when_file_exists(tmp_path: Path) -> None:
    model_file = tmp_path / "models" / "llm" / "assistant-small-q4" / "model-q4.gguf"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"gguf")
    entry = ensure_models.ModelEntry(
        family="llm",
        name="assistant-small-q4",
        config={
            "local_path": str(model_file),
            "source": {
                "type": "huggingface",
                "repo_id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
                "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
            },
        },
    )

    result = ensure_models._verify_entry(entry)

    assert result["ready"] is True
    assert result["present"] == ["model-q4.gguf"]
    assert result["missing"] == []
    assert result["degraded_reason"] is None


def test_ensure_entry_skips_ready_llm_artifact(tmp_path: Path, monkeypatch) -> None:
    model_file = tmp_path / "models" / "llm" / "assistant-small-q4" / "model-q4.gguf"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"gguf")
    entry = ensure_models.ModelEntry(
        family="llm",
        name="assistant-small-q4",
        config={
            "local_path": str(model_file),
            "source": {
                "type": "huggingface",
                "repo_id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
                "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
            },
        },
    )
    monkeypatch.setattr(
        ensure_models,
        "_download_huggingface",
        lambda entry, dry_run: (_ for _ in ()).throw(AssertionError("ready model must not be downloaded")),
    )

    result = ensure_models._ensure_entry(entry, dry_run=False)

    assert result["ready"] is True
    assert result["acquired"] == []


def test_verify_entry_directory_with_dot_in_name_reports_present_files(tmp_path: Path) -> None:
    model_root = tmp_path / "models" / "tts" / "kokoro-v1.0-onnx"
    model_root.mkdir(parents=True)
    (model_root / "kokoro-v1.0.onnx").write_bytes(b"onnx")
    (model_root / "voices-v1.0.bin").write_bytes(b"voices")
    entry = ensure_models.ModelEntry(
        family="tts",
        name="kokoro-v1.0-onnx",
        config={
            "local_path": str(model_root),
            "source": {
                "type": "url",
                "files": {
                    "kokoro-v1.0.onnx": "https://example.invalid/kokoro-v1.0.onnx",
                    "voices-v1.0.bin": "https://example.invalid/voices-v1.0.bin",
                },
            },
        },
    )

    result = ensure_models._verify_entry(entry)

    assert result["ready"] is True
    assert result["present"] == ["kokoro-v1.0.onnx", "voices-v1.0.bin"]
    assert result["missing"] == []


def test_verify_llm_single_file_artifact_reports_degraded_when_missing(tmp_path: Path) -> None:
    model_file = tmp_path / "models" / "llm" / "assistant-small-q4" / "model-q4.gguf"
    entry = ensure_models.ModelEntry(
        family="llm",
        name="assistant-small-q4",
        config={
            "local_path": str(model_file),
            "source": {
                "type": "huggingface",
                "repo_id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
                "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
            },
        },
    )

    result = ensure_models._verify_entry(entry)

    assert result["ready"] is False
    assert result["missing"] == ["model-q4.gguf"]
    assert result["degraded_reason"] == "Degraded-no-local-model-artifact"


def test_ensure_llm_single_file_huggingface_dry_run_uses_catalog_file(tmp_path: Path) -> None:
    model_file = tmp_path / "models" / "llm" / "assistant-small-q4" / "model-q4.gguf"
    entry = ensure_models.ModelEntry(
        family="llm",
        name="assistant-small-q4",
        config={
            "local_path": str(model_file),
            "source": {
                "type": "huggingface",
                "repo_id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
                "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
            },
        },
    )

    result = ensure_models._ensure_entry(entry, dry_run=True)

    assert result["family"] == "llm"
    assert result["model"] == "assistant-small-q4"
    assert result["dry_run"] is True
    assert result["acquired"] == ["model-q4.gguf"]
    assert result["ready"] is True


def test_ensure_family_acquires_wake_model_on_linux_host(monkeypatch) -> None:
    entry = ensure_models.ModelEntry(
        family="wake",
        name="openwakeword-hey-jarvis",
        config={
            "source": {"type": "url", "files": {}},
            "local_path": "models/wake/openwakeword",
        },
    )
    monkeypatch.setattr(ensure_models, "list_models", lambda family: {entry.name: entry.config})
    monkeypatch.setattr(
        ensure_models,
        "_ensure_entry",
        lambda entry, dry_run: {
            "family": entry.family,
            "model": entry.name,
            "acquired": ["hey_jarvis_v0.1.onnx"],
            "missing": [],
            "ready": True,
        },
    )

    code, result = ensure_models._ensure_family(
        "wake",
        None,
        dry_run=False,
        hardware_profile=HardwareProfile(os_name="linux", arch="amd64"),
    )

    assert code == 0
    assert result["models"][0]["ready"] is True
    assert result["models"][0]["acquired"] == ["hey_jarvis_v0.1.onnx"]
