from __future__ import annotations

import io
import zipfile
from pathlib import Path

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
