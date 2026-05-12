from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from backend.app.hardware.qnn_provider import create_qnn_session
from backend.app.models.catalog import get_model_path
from backend.app.runtimes.stt.base import STTBase


QNN_STT_DEFERRED_REASON = "QNN STT runtime active"


def providers_for_device(device: str) -> list[str]:
    if device == "cpu":
        return ["CPUExecutionProvider"]
    if device == "cuda":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if device == "directml":
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    if device == "qnn":
        return []
    raise ValueError(f"unsupported STT device '{device}'")


class OnnxWhisperRuntime(STTBase):
    def __init__(
        self,
        device: str = "cpu",
        model_path: Path | None = None,
        model_name: str | None = None,
    ) -> None:
        super().__init__(device=device, model_path=model_path or get_model_path("stt", model_name))
        self.model_name = model_name
        self.providers = providers_for_device(device)
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self.device == "qnn":
            raise NotImplementedError(QNN_STT_DEFERRED_REASON)
        if self._model is None:
            import onnx_asr

            self._model = onnx_asr.load_model(
                "onnx-community/whisper-small",
                path=self.model_path,
                providers=self.providers,
            )
        return self._model

    def is_available(self) -> bool:
        if self.device == "qnn":
            return False
        required = (
            "encoder_model.onnx",
            "decoder_model_merged.onnx",
            "config.json",
            "generation_config.json",
            "preprocessor_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.json",
            "merges.txt",
            "normalizer.json",
            "added_tokens.json",
        )
        return all((self.model_path / filename).is_file() for filename in required)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if self.device == "qnn":
            raise NotImplementedError(QNN_STT_DEFERRED_REASON)
        if not self.is_available():
            raise RuntimeError(f"STT model files are unavailable at {self.model_path}")
        waveform = np.asarray(audio, dtype=np.float32)
        result = self._load_model().recognize(waveform, sample_rate=sample_rate)
        if isinstance(result, str):
            return result
        return str(result)


class QnnWhisperRuntime(STTBase):
    """QNN-accelerated Whisper STT runtime for Snapdragon X Elite and compatible targets.

    Uses precompiled QNN context binaries paired with ONNX model files.
    Requires onnxruntime-qnn package and QAIRT SDK for QNN execution provider.
    """

    def __init__(
        self,
        device: str = "qnn",
        model_path: Path | None = None,
        model_name: str | None = None,
    ) -> None:
        if device != "qnn":
            raise ValueError(f"QnnWhisperRuntime requires device='qnn', got '{device}'")
        super().__init__(device=device, model_path=model_path or get_model_path("stt", model_name))
        self.model_name = model_name
        self._encoder_session: Any | None = None
        self._decoder_session: Any | None = None
        self._feature_extractor: Any | None = None
        self._tokenizer: Any | None = None

    def _ensure_preprocessors(self) -> None:
        if self._feature_extractor is None or self._tokenizer is None:
            from transformers import WhisperFeatureExtractor, WhisperTokenizer

            self._feature_extractor = WhisperFeatureExtractor.from_pretrained("openai/whisper-base")
            self._tokenizer = WhisperTokenizer.from_pretrained("openai/whisper-base")

    def _find_model_file(self, filename: str) -> Path:
        """Find required model file by name (handles nested directories)."""
        candidates = sorted(path for path in self.model_path.rglob(filename) if path.is_file())
        if not candidates:
            raise FileNotFoundError(f"missing required model file '{filename}' under {self.model_path}")
        return candidates[0]

    def _load_encoder_session(self) -> Any:
        """Load encoder session with QNN provider."""
        if self._encoder_session is None:
            encoder_path = self._find_model_file("encoder.onnx")
            self._encoder_session, _ = create_qnn_session(encoder_path, disable_cpu_fallback=True)
        return self._encoder_session

    def _load_decoder_session(self) -> Any:
        """Load decoder session with QNN provider."""
        if self._decoder_session is None:
            decoder_path = self._find_model_file("decoder.onnx")
            self._decoder_session, _ = create_qnn_session(decoder_path, disable_cpu_fallback=True)
        return self._decoder_session

    def is_available(self) -> bool:
        """Check if all required model files are present."""
        required = (
            "encoder.onnx",
            "decoder.onnx",
        )
        return all(any(path.is_file() for path in self.model_path.rglob(filename)) for filename in required)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if not self.is_available():
            raise RuntimeError(f"STT model files are unavailable at {self.model_path}")
        self._ensure_preprocessors()

        encoder = self._load_encoder_session()
        decoder = self._load_decoder_session()

        if encoder.get_providers()[0] != "QNNExecutionProvider":
            raise RuntimeError("QNNExecutionProvider not primary; CPU fallback detected")
        if decoder.get_providers()[0] != "QNNExecutionProvider":
            raise RuntimeError("QNNExecutionProvider not primary; CPU fallback detected")

        waveform = np.asarray(audio, dtype=np.float32)
        features = self._feature_extractor(
            waveform,
            sampling_rate=sample_rate,
            return_tensors="np",
        ).input_features.astype(np.float16)

        encoder_inputs = encoder.get_inputs()
        encoder_outputs = encoder.get_outputs()
        encoder_feed: dict[str, np.ndarray] = {encoder_inputs[0].name: features}
        encoder_values = encoder.run(None, encoder_feed)
        encoder_map = {output.name: value for output, value in zip(encoder_outputs, encoder_values, strict=False)}
        decoder_input_names = [i.name for i in decoder.get_inputs()]
        print("[QNN_STT_DEBUG] encoder_map.keys=", list(encoder_map.keys()))
        print("[QNN_STT_DEBUG] decoder_input_names=", decoder_input_names)

        token_ids: list[int] = [50258]  # <|startoftranscript|>
        max_new_tokens = 448
        eot_token = 50257

        decoder_input_defs = {i.name: i for i in decoder.get_inputs()}
        decoder_output_defs = {o.name: o for o in decoder.get_outputs()}

        def _norm_tokens(name: str) -> list[str]:
            cleaned = name.replace("_in", "").replace("_out", "")
            return [part for part in cleaned.split("_") if part]

        self_cache_pairs: dict[str, str] = {}
        self_cache_inputs = [name for name in decoder_input_defs if "cache_self" in name]
        self_cache_outputs = [name for name in decoder_output_defs if "cache_self" in name]
        output_token_sets = {name: set(_norm_tokens(name)) for name in self_cache_outputs}
        for in_name in self_cache_inputs:
            in_tokens = set(_norm_tokens(in_name))
            candidates = [
                out_name
                for out_name in self_cache_outputs
                if out_name not in self_cache_pairs.values() and in_tokens.issubset(output_token_sets[out_name])
            ]
            if not candidates:
                raise RuntimeError(f"unable to map decoder self-cache input '{in_name}' to output")
            candidates.sort(key=lambda n: len(output_token_sets[n]))
            self_cache_pairs[in_name] = candidates[0]

        def _layer_idx(name: str) -> str | None:
            parts = name.split("_")
            for i, part in enumerate(parts):
                if part == "cross" and i + 1 < len(parts):
                    return parts[i + 1]
            return None

        def _kv_kind(name: str) -> str:
            tokens = set(_norm_tokens(name))
            if "key" in tokens or ("k" in tokens and "cache" in tokens):
                return "k"
            if "value" in tokens or "v" in tokens:
                return "v"
            return ""

        cross_cache_pairs: dict[str, str] = {}
        cross_inputs = [name for name in decoder_input_defs if "cross" in name]
        cross_outputs = [name for name in encoder_map if "cross" in name]
        for in_name in cross_inputs:
            in_layer = _layer_idx(in_name)
            in_kv = _kv_kind(in_name)
            candidates = [
                out_name
                for out_name in cross_outputs
                if _layer_idx(out_name) == in_layer and _kv_kind(out_name) == in_kv
            ]
            if not candidates:
                raise RuntimeError(f"unmatched decoder cross-cache input '{in_name}'")
            candidates.sort()
            cross_cache_pairs[in_name] = candidates[0]

        cache_state: dict[str, np.ndarray] = {}
        first_step_decoder_keys: list[str] | None = None
        first_step_cache_keys: list[str] | None = None

        for step_idx in range(max_new_tokens):
            last_token = np.array([[token_ids[-1]]], dtype=np.int32)
            decoder_feed: dict[str, np.ndarray] = {}

            for name, input_def in decoder_input_defs.items():
                if name == "input_ids":
                    decoder_feed[name] = last_token
                    continue
                if name == "attention_mask":
                    mask_shape = [
                        1 if dim is None or isinstance(dim, str) else int(dim) for dim in (input_def.shape or [])
                    ]
                    mask_dtype = np.int32 if input_def.type == "tensor(int32)" else np.float16
                    decoder_feed[name] = np.ones(mask_shape, dtype=mask_dtype)
                    continue
                if name == "position_ids":
                    decoder_feed[name] = np.array([len(token_ids) - 1], dtype=np.int32)
                    continue

                if name in cache_state:
                    decoder_feed[name] = cache_state[name]
                    continue
                if name in cross_cache_pairs:
                    decoder_feed[name] = np.asarray(encoder_map[cross_cache_pairs[name]], dtype=np.float16)
                    continue
                if "cross" in name:
                    raise RuntimeError(f"unmapped decoder cross-cache input '{name}'")

                shape = [1 if dim is None or isinstance(dim, str) else int(dim) for dim in (input_def.shape or [])]
                dtype = np.int32 if input_def.type == "tensor(int32)" else np.float16
                decoder_feed[name] = np.zeros(shape, dtype=dtype)

            decoder_values = decoder.run(None, decoder_feed)
            decoder_map = {
                output_name: value
                for output_name, value in zip(decoder_output_defs.keys(), decoder_values, strict=False)
            }

            logits_name = next(name for name in decoder_map if "logits" in name)
            logits = np.asarray(decoder_map[logits_name])
            next_token = int(np.argmax(logits[:, :, 0, 0], axis=1)[0])

            for in_name, out_name in self_cache_pairs.items():
                if out_name not in decoder_map:
                    raise RuntimeError(f"missing expected decoder self-cache output '{out_name}'")
                cache_state[in_name] = np.asarray(decoder_map[out_name])

            if step_idx == 0:
                first_step_decoder_keys = list(decoder_map.keys())
                first_step_cache_keys = list(cache_state.keys())

            if next_token == eot_token:
                break
            token_ids.append(next_token)

        transcript = self._tokenizer.decode(token_ids, skip_special_tokens=True)
        result = transcript.strip().lower()
        if not result:
            print("[QNN_STT_DEBUG] decoder_map.keys(step1)=", first_step_decoder_keys)
            print("[QNN_STT_DEBUG] cache_state.keys(step1)=", first_step_cache_keys)
            print("[QNN_STT_DEBUG] token_ids=", token_ids)
            print("[QNN_STT_DEBUG] return_value=", result)
        return result