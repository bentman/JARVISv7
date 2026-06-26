Most aligned path: **treat the 6/22 `onnxruntime-qnn 2.3.0` release as the new normal ARM64 QNN path, remove repo-local QNN special casing, and make ARM64 provisioning look like AMD64: `>=` package specs, resolver-driven extras, no post-install force-reinstall workaround, no “onnxruntime conflicts with onnxruntime-qnn” rule.**

## Why this is now reasonable

Upstream now has the missing package story. PyPI lists `onnxruntime-qnn 2.3.0`, released June 22, 2026, with Python `>=3.11` and Windows ARM64 wheels for CPython 3.11–3.14. ([PyPI][1]) The 2.3.0 release notes say ONNX Runtime compatibility is `>=1.24.1`, compiled with `v1.24.4`, QAIRT SDK compatibility is `2.47.0`, and the official install example is:

```text
pip install onnxruntime==1.24.4
pip install onnxruntime-qnn==2.3.0
```

([GitHub][2])

That directly conflicts with the repo’s current workaround logic, which uninstalls `onnxruntime`, force-reinstalls `onnxruntime-qnn==1.24.3 --no-deps`, and treats `onnxruntime` + `onnxruntime_qnn` as a conflict.

## Clean Codex task path

1. **Change `pyproject.toml` ARM64 QNN extra to unpinned `>=` specs.**

Current:

```toml
"onnxruntime-qnn==1.24.3; platform_machine=='ARM64' and sys_platform=='win32'",
"onnx>=1.16; platform_machine=='ARM64' and sys_platform=='win32'",
"transformers>=4.40; platform_machine=='ARM64' and sys_platform=='win32'",
```

Recommended:

```toml
"onnxruntime>=1.24.4; platform_machine=='ARM64' and sys_platform=='win32'",
"onnxruntime-qnn>=2.3.0; platform_machine=='ARM64' and sys_platform=='win32'",
"onnx>=1.16; platform_machine=='ARM64' and sys_platform=='win32'",
"transformers>=4.40; platform_machine=='ARM64' and sys_platform=='win32'",
```

This aligns ARM64 with the AMD64 pattern: no exact pin, resolver chooses the extra, pip resolves the current compatible package. The repo’s current `pyproject.toml` explicitly pins only QNN and otherwise uses `>=` for ORT-family packages.

2. **Update `backend/app/hardware/provisioning.py` to match.**

Current `_EXTRA_REQUIREMENT_SPECS` hardcodes `onnxruntime-qnn==1.24.3`.  Replace with:

```python
"hw-npu-qualcomm-qnn": (
    "onnxruntime>=1.24.4",
    "onnxruntime-qnn>=2.3.0",
    "onnx>=1.16",
    "transformers>=4.40",
),
```

Do not change resolver architecture. The resolver already correctly adds `hw-npu-qualcomm-qnn` for ARM64 Qualcomm NPU and omits the ARM64 CPU ORT extra when an accelerated ORT path exists.

3. **Remove the QNN force-reinstall workaround from `scripts/provision.py`.**

Delete the ARM64 QNN branch that uninstalls `onnxruntime` and force-reinstalls `onnxruntime-qnn==1.24.3 --no-deps`.  Let the normal editable install do the work:

```text
pip install -e .[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev]
```

Keep the CUDA special handling if still required for AMD64, but QNN should no longer be special-cased.

4. **Remove the verify conflict rule.**

Current verify rejects having both `onnxruntime` and `onnxruntime_qnn` installed on ARM64 QNN hosts.  That is now backwards relative to the 2.3.0 release notes, which explicitly install both. ([GitHub][2])

Remove:

```python
if arm64_qnn_profile and {"onnxruntime", "onnxruntime_qnn"} <= installed_requirements:
    conflicts.append("onnxruntime cannot be installed alongside onnxruntime-qnn on ARM64 QNN hosts")
```

5. **Update tests that encode the old workaround.**

Known gotchas:

`backend/tests/unit/hardware/test_provisioning.py` currently asserts QNN excludes `onnxruntime`, includes exact `onnxruntime-qnn==1.24.3`, and includes no paired ORT package.  Update to expect both `onnxruntime` and `onnxruntime-qnn`, with `>=` specs.

`backend/tests/unit/scripts/test_provision_script.py` has a test named `test_arm64_qnn_install_reinstalls_pinned_qnn_family` that expects uninstall + force-reinstall + `--no-deps` + `onnxruntime-qnn==1.24.3`.  Replace with a test proving no QNN post-install workaround runs.

`test_verify_reports_version_drift_for_exact_pins` currently mocks an exact `onnxruntime_qnn: 1.24.3` expected version.  With no exact pin, this should become a test that verify does not require exact QNN version when specs are `>=`.

`test_verify_rejects_base_onnxruntime_with_arm64_qnn` should be deleted or inverted: paired `onnxruntime` + `onnxruntime_qnn` should be accepted.

6. **Do not touch QNN runtime logic in this pass.**

`QnnWhisperRuntime` already uses `create_qnn_session()`, checks that `QNNExecutionProvider` is primary, and disables CPU fallback through `create_qnn_session`.  The provider helper already uses `backend_path` and `session.disable_cpu_ep_fallback`.  ONNX Runtime’s docs validate both patterns. ([ONNX Runtime][3])

This slice should be dependency/provisioning alignment only. Runtime tuning can come after the package stack is sane.

## Validation target for Codex

Minimum non-exploratory validation:

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/unit/hardware/test_provisioning.py backend/tests/unit/scripts/test_provision_script.py -q
backend\.venv\Scripts\python scripts\provision.py dry-run
backend\.venv\Scripts\python scripts\provision.py install --dry-run
backend\.venv\Scripts\python scripts\provision.py verify
backend\.venv\Scripts\python scripts\validate_backend.py unit
backend\.venv\Scripts\python scripts\validate_backend.py regression
```

ARM64 live proof, only after the above is green:

```powershell
backend\.venv\Scripts\python scripts\validate_backend.py profile
backend\.venv\Scripts\python scripts\validate_backend.py runtime --families stt --devices qnn
```

## Keep separate from this task

Do not solve the NumPy/sounddevice warning here. The current bug is real, but it is orthogonal. `sounddevice 0.5.5` under `numpy=2.5.0` produced the ARM64 live warning noise, and the warning is inside third-party `sounddevice.py`, not repo-owned reshape logic.  A NumPy ceiling or warning filter is a separate audio dependency hygiene slice.

## Bottom line

Codex should implement the upstream-aligned QNN dependency path, not trial more QNN runtime code:

```text
pyproject: onnxruntime>=1.24.4 + onnxruntime-qnn>=2.3.0
provisioning resolver: same specs
provision script: remove QNN uninstall/force-reinstall/no-deps path
verify: allow paired onnxruntime + onnxruntime-qnn
tests: remove exact-pin and conflict assumptions
runtime: leave QnnWhisperRuntime/qnn_provider unchanged
```

That is the clearest path to AMD64-style alignment with the fewest workarounds.

[1]: https://pypi.org/project/onnxruntime-qnn/ "onnxruntime-qnn · PyPI"
[2]: https://github.com/onnxruntime/onnxruntime-qnn/releases/tag/v2.3.0 "Release ONNX Runtime QNN Execution Provider v2.3.0 · onnxruntime/onnxruntime-qnn · GitHub"
[3]: https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html "Qualcomm - QNN | onnxruntime"
