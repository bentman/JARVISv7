## Determination

The ARM64 Agent should **not** revert to old QNN pins, uninstall/reinstall paths, `--no-deps`, or `<1.25` constraints. The correct configuration remains the Slice U split-package configuration:

```toml
onnxruntime>=1.24.4
onnxruntime-qnn>=2.3.0
onnx>=1.16
transformers>=4.40
```

The repo currently has that configuration in `pyproject.toml`, and it should stay.

The U2 report proves the old blocker was resolved: `onnxruntime_qnn` exposes provider-library helpers, the package includes `onnxruntime_providers_qnn.dll`, `QnnHtp.dll`, and related QNN DLLs, and explicit registration makes `QNNExecutionProvider` appear in `onnxruntime.get_available_providers()`.

So the remaining failure is **not dependency configuration**. It is **model artifact compatibility / EPContext acceptance** for the current precompiled Whisper QNN artifact.

## What changed correctly

The U2 code adds a real provider activation helper. It imports `onnxruntime_qnn`, finds `onnxruntime_providers_qnn.dll`, adds the QNN package directory to the DLL search path, and registers `QNNExecutionProvider` through `onnxruntime.register_execution_provider_library(...)`.

Preflight now calls that activation before provider probing on Qualcomm QNN profiles and records observable tokens/logs such as `qnn:provider_library_registered`, `QNNProvider:added`, and `QNNProvider:library`.

`create_qnn_session()` also activates QNN before creating the session and still keeps CPU fallback disabled. That invariant is correct for proof: if QNN cannot claim the graph, the live QNN test should fail instead of silently running on CPU.

The report confirms profile validation now emits the intended QNN evidence: `qnn:provider_library_registered`, `ep:QNNExecutionProvider`, `import:onnxruntime-qnn`, packaged `QnnHtp.dll`, and `dll:QnnHtp`.  The live QNN hardware gate also passed.

## Why the old workaround path is wrong

The live STT failure now occurs after provider registration:

```text
This session contains graph nodes that are assigned to the default CPU EP,
but fallback to CPU EP has been explicitly disabled by the user.
```

The failed model is the current precompiled STT artifact under:

```text
models\stt\whisper-base-en-qnn-snapdragon-x-elite\...\encoder.onnx
```

That means ONNX Runtime can see `QNNExecutionProvider`, but QNN EP is not claiming the current `encoder.onnx` EPContext node. Reverting packages would be guessing against evidence.

ONNX Runtime’s EPContext design says QNN EP only accepts EPContext nodes whose `source` attribute is `QNN` or `QnnExecutionProvider`, and context binaries are referenced through the EPContext node’s `ep_cache_context` attribute. ([ONNX Runtime][1]) It also says that for file-path model loading, the EP should use the model file’s folder plus the relative context-binary path; `ep.context_file_path` is only required when loading the model from a memory buffer. ([ONNX Runtime][1])

The report says the artifact consists of one-node EPContext wrappers plus adjacent QAIRT context binaries, and local probes adding metadata such as `main_context=1`, `source`, and `ep_context_type` did not make QNN claim the node.  That points to artifact generation/version/format compatibility, not install policy.

## Appropriate configuration

Keep this dependency/provisioning configuration:

```text
pyproject.toml: keep onnxruntime>=1.24.4 and onnxruntime-qnn>=2.3.0
backend/app/hardware/provisioning.py: keep paired ORT/QNN requirement specs
scripts/provision.py: keep normal editable install; do not add ARM64 QNN post-install surgery
scripts/provision.py verify: keep paired onnxruntime + onnxruntime_qnn allowed
backend/app/hardware/qnn_provider.py: keep provider registration helper
backend/app/hardware/preflight.py: keep activation before provider probing
```

Do **not** add:

```text
onnxruntime-qnn==1.24.3
onnxruntime==1.24.3
onnxruntime<1.25
--no-deps
force-reinstall QNN
uninstall onnxruntime on ARM64 QNN hosts
CPU fallback for QNN proof
metadata mutation of model artifacts in repo
```

The 2.3.0 upstream release explicitly says ONNX Runtime QNN EP v2.3.0 is compatible with ONNX Runtime `>=1.24.1`, compiled with `1.24.4`, and uses QAIRT SDK `2.47.0`; it also lists paired installation of `onnxruntime==1.24.4` and `onnxruntime-qnn==2.3.0`, plus Windows ARM64 Python wheel support for inference. ([GitHub][2]) The repo’s `>=1.24.4` / `>=2.3.0` policy is consistent with that, and the U2 activation proof shows the split package works.

## Correct next action

Move the next slice from “QNN package/config fix” to **QNN STT artifact compatibility**.

Minimal task statement for Codex Agent:

```text
Do not change pyproject.toml, provisioning.py, or scripts/provision.py.

Keep QNN provider activation as implemented. Investigate why the current
whisper-base-en-qnn-snapdragon-x-elite EPContext wrapper is not claimed by
QNNExecutionProvider under onnxruntime-qnn>=2.3.0.

Validate the current encoder.onnx and decoder.onnx EPContext attributes:
source, ep_cache_context, embed_mode, main_context, partition_name, and
relative context-binary paths. Compare them against ONNX Runtime EPContext
requirements. If the artifact is incompatible, mark the current model entry
as not QNN-ready and add a new model-acquisition target for a current
QAIRT/onnxruntime-qnn 2.3-compatible Whisper QNN artifact.

Do not patch model metadata unless a documented ORT/QNN requirement is
missing and the patched model is generated reproducibly from source/artifact
metadata. Do not commit local binary edits.
```

The most likely durable fix is **replace/regenerate the QNN Whisper artifact** so its EPContext wrappers and context binaries match the current QNN EP expectations. The current `config/models/stt.yaml` points to a static QAI Hub public asset `v0.53.1` for `whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite.zip`.  That is now the suspicious component, not the QNN package stack.

## Recommended close-state language

Current U2 state should be recorded as:

```text
QNN provider activation: PASS
QNN hardware gate: PASS
QNN STT runtime proof: FAIL-artifact-incompatible
Dependency/provisioning configuration: KEEP
Fallback behavior: KEEP CPU fallback unless QNN provider + model proof pass
```

Do not mark active QNN STT as complete until `test_stt_qnn_live_transcript_correct` passes with CPU fallback disabled.

[1]: https://onnxruntime.ai/docs/execution-providers/EP-Context-Design.html "EP Context Design | onnxruntime"
[2]: https://github.com/onnxruntime/onnxruntime-qnn/releases/tag/v2.3.0 "Release ONNX Runtime QNN Execution Provider v2.3.0 · onnxruntime/onnxruntime-qnn · GitHub"
