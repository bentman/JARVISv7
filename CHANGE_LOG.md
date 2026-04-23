# CHANGE_LOG.md
> :
> No edits/reorders/deletes of past entries. If an entry is wrong, append a corrective entry.

## Rules
- Write an entry only after task objective is “done” and supported by evidence.
- **Ordering:** Entries are maintained in **descending chronological order** (newest first, oldest last).
- **Append location:** New entries must be added **at the top of the Entries section**, directly under `## Entries`.
- Each entry must include:
  - Timestamp: `YYYY-MM-DD HH:MM`
  - Summary: 1–2 lines, past tense
  - Scope: files/areas touched
  - Host class(es): validated on (e.g., `Windows x64`, `Windows ARM64`, or both)
  - Evidence: exact command(s) run + a minimal excerpt pointer (or embedded excerpt ≤10 lines)
- If a change is reverted, append a new entry describing the revert and why.

---

## Entries

- 2026-04-23 14:31
  - Summary: Sub-Slice A.4 added the arch-aware test harness scaffolding and the script-level validator/bootstrap/ensure-models entry points.
  - Scope: `backend/tests/conftest.py`, `backend/tests/integration/__init__.py`, `backend/tests/runtime/__init__.py`, `backend/tests/runtime/hardware/__init__.py`, `backend/tests/runtime/acceleration_matrix/__init__.py`, `backend/tests/fixtures/__init__.py`, `scripts/validate_backend.py`, `scripts/bootstrap.py`, `scripts/ensure_models.py`, `backend/tests/unit/scripts/test_validate_backend_script.py`, `backend/tests/unit/scripts/test_bootstrap_script.py`
  - Host class(es): Windows host (current workspace)
  - Evidence: `backend/.venv/Scripts/python -m compileall scripts backend/tests`; `backend/.venv/Scripts/python scripts/validate_backend.py --help`; `backend/.venv/Scripts/python scripts/bootstrap.py --help`; `backend/.venv/Scripts/python scripts/ensure_models.py`
    ```text
    [CHECKPOINT 1/5] profile -> PASS ...
    No module named pytest
    ```
  - Note: `pytest` was still missing in `backend/.venv` during validation.
- 2026-04-23 14:31
  - Summary: Sub-Slice A.3 added the hardware preflight rail and readiness derivation helpers.
  - Scope: `backend/app/hardware/preflight.py`, `backend/app/hardware/readiness.py`, `backend/tests/unit/hardware/test_preflight.py`, `backend/tests/unit/hardware/test_readiness.py`
  - Host class(es): Windows host (current workspace)
  - Evidence: `backend/.venv/Scripts/python -m compileall backend/app/hardware backend/tests/unit/hardware`; dependency-free smoke for preflight cache and readiness tuple output
    ```text
    ('cuda', True, 'ep:CUDAExecutionProvider proven; selecting cuda')
    ```
  - Note: `pytest` was still missing in `backend/.venv` during validation.
- 2026-04-23 14:31
  - Summary: Sub-Slice A.2 added the declarative provisioning resolver, provisioning script, and supporting core helpers.
  - Scope: `backend/app/core/paths.py`, `backend/app/core/logging.py`, `backend/app/core/settings.py`, `backend/app/hardware/provisioning.py`, `scripts/provision.py`, `backend/tests/unit/hardware/test_provisioning.py`, `backend/tests/unit/scripts/test_provision_script.py`
  - Host class(es): Windows host (current workspace)
  - Evidence: `backend/.venv/Scripts/python -m compileall backend/app/core backend/app/hardware scripts/provision.py backend/tests/unit`; dependency-free smoke for `dry-run`, `install --dry-run`, `verify`, and `lock`
    ```text
    dry_run_code= 0
    install_dry_code= 0
    verify_code= 1
    lock_code= 0
    ```
  - Note: `pytest` was still missing in `backend/.venv` during validation.
- 2026-04-23 14:31
  - Summary: Sub-Slice A.1 added the hardware capability profile and detector layer.
  - Scope: `backend/app/core/capabilities.py`, `backend/app/hardware/__init__.py`, `backend/app/hardware/detectors/__init__.py`, `backend/app/hardware/detectors/cpu_detector.py`, `backend/app/hardware/detectors/memory_detector.py`, `backend/app/hardware/detectors/os_detector.py`, `backend/app/hardware/detectors/gpu_detector.py`, `backend/app/hardware/detectors/cuda_detector.py`, `backend/app/hardware/detectors/npu_detector.py`, `backend/app/hardware/profiler.py`, `backend/tests/unit/hardware/test_profiler.py`
  - Host class(es): Windows host (current workspace)
  - Evidence: `backend/.venv/Scripts/python -m compileall backend/app/core backend/app/hardware backend/tests`; dependency-free smoke for `run_profiler()`
    ```text
    PASS A.1 smoke
    ```
  - Note: `pytest` was still missing in `backend/.venv` during validation.
- 2026-04-22 14:15
  - Summary: CHANGE_LOG.md established
  - Scope: CHANGE_LOG.md
  - Evidence: `cat .\CHANGE_LOG.md -head 1`
    ```text
    # CHANGE_LOG.md
    ```
