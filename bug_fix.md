# Bug Fix Notes

## 2026-06-17 — Agent ledger ordering is nondeterministic

### Status

Proposed, not implemented.

### Observation

`backend\.venv\Scripts\python scripts\validate_backend.py unit` intermittently failed in agent tests, then passed on rerun.

Observed failures:

- `backend/tests/unit/agents/test_creator.py::test_agent_creator_writes_valid_disabled_spec_file`
- `backend/tests/unit/agents/test_critic.py::test_critic_dry_run_reviews_existing_records`

### Root Cause

`backend/app/agents/ledger.py::AgentLedger.list_by_trace()` and `list_by_turn()` order rows by `created_at ASC, record_id ASC`.

Records appended in the same fast operation can share the same `created_at` timestamp. `record_id` is UUID/random, so it is not an insertion-order tiebreaker. That can reorder records and make tests or consumers that expect append order nondeterministic.

### Proposed Fix

- Add an insertion-order column, for example `sequence_id INTEGER PRIMARY KEY AUTOINCREMENT`.
- Keep `record_id` as `TEXT UNIQUE NOT NULL`.
- Order ledger reads by `sequence_id ASC`.
- Add a migration path for existing ledger databases that lack `sequence_id`.
- Add a focused unit test that appends multiple records with identical `created_at` and confirms read order matches append order.

### Evidence

- Full unit suite failed twice with different agent ledger ordering assertions.
- The isolated first failing test passed on rerun.
- A later full unit rerun passed: `495 passed, 1 skipped`.

