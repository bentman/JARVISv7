Read in full: `hardware/{profiler,provisioning,preflight,readiness,qnn\_provider}.py`, `detectors/\*`, `core/capabilities.py`, `pyproject.toml`, `config/models/\*.yaml`, `models/catalog.py`, `scripts/{provision,ensure\_models}.py`, and all four `runtimes/{stt,tts,vad,wake}/\*`.



\## v7 separates four stages. AWF collapsed them into one string.



| Stage | File | Input | Output |

|---|---|---|---|

| 1. Profile | `hardware/profiler.py` + `detectors/\*` | OS/CPU/memory/GPU/CUDA/NPU probes — \*\*no ONNX Runtime involvement at all\*\* | `HardwareProfile` (`gpu\_vendor`, `cuda\_available`, `npu\_vendor`, …) |

| 2. Provision | `hardware/provisioning.py` + pyproject extras | `HardwareProfile` | list of extras → which ORT wheel gets installed |

| 3. Preflight | `hardware/preflight.py` | installed extras | tokens: `import:onnxruntime`, `ep:CUDAExecutionProvider`, `dll:QnnHtp`, `opencl:adreno` |

| 4. Readiness | `hardware/readiness.py` | profile \*\*and\*\* tokens | `(device, ready, reason)` \*\*per family\*\* |



`cuda\_available` comes from `nvidia-smi`/`nvcc` — hardware. `ep:CUDAExecutionProvider` comes from `get\_available\_providers()` — installed wheel. v7 keeps them apart and requires agreement:



```python

if profile.gpu\_vendor == "nvidia" and profile.cuda\_available and \_has\_token(preflight, "ep:CUDAExecutionProvider"):

&#x20;   return ("cuda", True, "ep:CUDAExecutionProvider proven; selecting cuda")

```



AWF has only the third signal. That is why `cuda\_verified: False` is unreadable — it cannot distinguish absent hardware from absent wheel.



\## Device selection is per family, not per host



Four independent functions: `derive\_stt\_device\_readiness`, `derive\_tts\_device\_readiness`, `derive\_wake\_device\_readiness`, `derive\_llm\_device\_readiness`. STT can be `qnn` while TTS is `cpu` and wake is always `cpu` (`import:openwakeword` → cpu, no accelerator branch). A single `windows-arm64-qnn` suffix cannot express that.



\*\*And it corrects something I wrote.\*\* I claimed TTS/VAD/wake have no per-profile variation. True of \*artifacts\*, false of \*device\*: `KokoroOnnxRuntime.\_load\_model` builds `rt.InferenceSession(onnx\_path, providers=\[...])` and `Kokoro.from\_session(...)` for cuda/directml/qnn — same two files, different provider. Artifact selection and device selection are separate axes. ADR-0007 merged them.



\## Voice model selection



`config/models/<family>.yaml`, keyed by \*\*model name\*\*, not profile ID:



```yaml

default\_model: whisper-small-onnx

models:

&#x20; whisper-small-onnx:

&#x20;   devices: \[cpu, cuda, directml]

&#x20;   source: {type: huggingface, repo\_id: ..., files: {...}}

&#x20;   local\_path: models/stt/whisper-small-onnx

&#x20; whisper-base-en-qnn-snapdragon-x-elite:

&#x20;   supported\_hosts: \[windows\_arm64]

&#x20;   devices: \[qnn]

&#x20;   source: {type: url\_zip, url: ...}

&#x20;   local\_path: models/stt/whisper-base-en-qnn-snapdragon-x-elite

```



`supported\_hosts` gates a model to a host class. `local\_path` gives each model its own directory so variants coexist. `devices` declares what the model can run on. No `sha256` on any voice model; no `revision`. The only sha256 in the whole catalog is on a llama.cpp \*source tarball\* for a from-source build.



\## Acquisition



`scripts/ensure\_models.py` dispatches on `source.type` (`url`, `huggingface`, `url\_zip`), verifies presence and non-zero size first and returns early if ready, and reports per-model `{present, missing, ready, degraded\_reason}`. `SKIP-unsupported-host:{os}\_{arch}` when `supported\_hosts` excludes the host. `scripts/provision.py` resolves extras from the profile, evaluates PEP 508 markers against a profile-derived environment, and runs `pip install -e .\[extras]`.



Also: v7 has \*\*no Silero VAD\*\*. `runtimes/vad/energy\_runtime.py` is RMS-threshold, no model file, no `vad.yaml`. AWF's ONNX VAD is AWF-only.



\## What this means for AWF



Five concrete defects, in dependency order:



1\. No provisioning stage. `onnxruntime` (CPU wheel) is a base dependency, so stage 3 can only ever answer CPU.

2\. The profiler conflates hardware facts with runtime capability. `hw\_profiler.py` collects `cuda\_available` from `nvidia-smi` in its inventory — and then throws it away, deciding purely on EP probes.

3\. One profile ID for all four functions, where four independent device decisions are needed.

4\. ADR-0007 keys artifacts by acceleration class, conflating artifact choice with device choice. The catalog should key by model name with host/device gating.

5\. `models/<function>/<name>` flat layout cannot hold two STT variants; v7 uses `local\_path` per model.



ADR-0006's profiler is stage 1 + a partial stage 3, fused. ADR-0007 is a partial stage 4 built on the fused output. Both need reworking against this split, and provisioning needs to exist first.



How do you want to sequence it — provisioning ADR first, then rewrite 0006 and 0007 against it, or one ADR covering the full four-stage split?

