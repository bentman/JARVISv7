# SYSTEM_INVENTORY.md
> Authoritative capability ledger. This is not a roadmap or config reference. 
> Inventory entries must reflect only observable artifacts in this repository: files, directories, executable code, configuration, scripts, and explicit UI text. 
> Do not include intent, design plans, or inferred behavior.

## Rules
- One component entry = one capability or feature observed in the repository.
- New capabilities go at the top under `## Inventory` and above `## Observed Initial Inventory`.
- Corrections or clarifications go only below the `## Appendix` section.
- Entries must include:

- Capability: **Brief Descriptive Component Name** 
  - Date/Time
  - State: Planned, Implemented, Verified, Deferred
  - Location: `Relative File Path(s)`
  - Validation: Method &/or `Relative Script Path(s)`; include host class(es) (e.g., `Windows x64`, `Windows ARM64`)
  - Notes: 
    - Optional (3 lines max).

## States
- Planned: intent only, not implemented
- Implemented: code exists, not yet validated end-to-end
- Verified: validated with evidence (command)
- Deferred: intentionally postponed (reason noted)

---

## Inventory

- Capability: Slice B cross-platform voice runtime foundation - 2026-04-26 19:45
  - State: Verified
  - Location: `backend/app/runtimes/stt/`, `backend/app/runtimes/tts/`, `backend/app/runtimes/llm/`, `backend/app/runtimes/wake/`, `backend/app/routing/runtime_selector.py`, `backend/app/models/catalog.py`, `config/models/`, `config/app/policies.yaml`, `backend/tests/runtime/voice/`, `backend/tests/unit/runtimes/`, `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`, `scripts/ensure_models.py`, `scripts/validate_backend.py`
  - Validation: Windows x64 and Windows ARM64 B.0-B.5 validation recorded in `CHANGE_LOG.md`; B.5 matrix validation recorded in `CHANGE_LOG.md` entry `2026-04-26 19:45`; x64 matrix artifact `reports/validation/b5-acceleration-matrix-current-host.txt`; x64 regression artifact `reports/validation/20260427004353-regression.txt`; ARM64 B.5 matrix state recorded in `CHANGE_LOG.md` entry `2026-04-26 19:45`.
  - Notes: STT, TTS, LLM, and Wake runtime families exist with device-parameterized runtime surfaces. CPU voice paths and B.5 matrix are validated on Windows x64 and Windows ARM64. QNN remains definition-only with STT inference deferred to H.2; llama.cpp remains deferred to H.1; no Group C/D/E/F/G/H/I implementation is claimed.

- Capability: Slice A hardware/provisioning/readiness foundation - 2026-04-24 17:16
  - State: Verified
  - Location: `backend/app/hardware/`, `backend/app/core/capabilities.py`, `scripts/provision.py`, `scripts/validate_backend.py`, `backend/tests/unit/hardware/`, `backend/tests/unit/scripts/`, `reports/diagnostics/`, `reports/validation/`
  - Validation: Windows x64 manual provisioning/profile/regression PASS; Windows ARM64 manual provisioning/profile/regression PASS; ARM64 A.6 regression PASS with `61 passed`
  - Notes: Covers A.1 profiler/capability flags, A.2 provisioning resolver/install path, A.3 preflight/readiness evidence, A.4 validation/report harness, A.5 x64/ARM64 clean-host validation proof, and A.6 QNN structural metadata/readiness definition only. QNN is not executable at Slice A; `import:onnxruntime-qnn` is present on ARM64; `ep:QNNExecutionProvider:MISSING` and `dll:QnnHtp:MISSING` are expected/not-proven states; STT readiness remains CPU-selected with the H.2-named QNN inference pending reason. No Group B runtime/model/voice-loop work, no STT/TTS/LLM/wake runtime execution, and no durable desktop/product surface were introduced. Codex temp/pytest cleanup failures remain tooling-context only, not repo acceptance evidence.

- Capability: SYSTEM_INVENTORY extablished - 2026-04-22 14:20
  - State: Implemented
  - Location: `SYSTEM_INVENTORY.md`
  - Validation: `cat .\SYSTEM_INVENTORY.md -head 1` = `# SYSTEM_INVENTORY.md`
  - Notes: 

---

## Appendix
