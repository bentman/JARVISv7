Task: Boundary language cleanup for vague "defer/deferred" wording and brittle slice references

Repository: bentman/JARVISv7
Start from current HEAD unless instructed otherwise.

Follow AGENTS.md exactly. This is primarily a documentation/control-language cleanup, not a feature implementation.

Problem:
The repo overuses "defer/deferred/deferred until/later/future slice" language in governing docs, changelog/inventory entries, config, and some code comments. This creates ambiguity and gives future agents room to avoid adjacent work or ignore available connectors.

A related problem is that many of these statements reference specific slice names, numbers, or phases adjacent to the deferred language, such as "deferred to M.1", "deferred until Slice N", "future Group M", or similar. Slice names and numbers change. Active guidance should identify stable capability boundaries, not brittle slice labels.

Goal:
Remove or sharply constrain vague defer wording in active guidance surfaces. Also remove brittle slice-name/number references when they are adjacent to defer/later/future-slice language. Preserve valid scope boundaries, but express them as clear capability state, stable ownership boundary, and current next-state.

Primary files to inspect:
- AGENTS.md
- SYSTEM_INVENTORY.md
- CHANGE_LOG.md
- slices.md
- ProjectVision.md
- backend/**/*.py comments containing defer/deferred/later/future
- config/**/*.yaml and config/**/*.md
- reports/validation/**/*.md only if current guidance depends on them
- docs/slices-done/**/*.md only after active docs are cleaned, and only for misleading stale language

Discovery:
Run a repository-wide search for:
- defer
- deferred
- defers
- deferring
- deferred until
- later
- future slice
- future group
- future phase
- not yet
- out of scope
- Slice
- Group
- M.1
- L.6
- N.
- any phrase matching "deferred to <slice/group/phase/name/number>"

Do not do a blind find/replace.

Classify every occurrence into one of these buckets:
1. Historical record — leave unless it now misleads active guidance.
2. Current inventory gap — rewrite to explicit current state and stable next owner.
3. Changelog ambiguity — rewrite to "not claimed", "not implemented", or "owned by <capability boundary>".
4. Code comment escape hatch — rewrite to exact current limitation or concrete TODO with boundary ownership.
5. Config placeholder — rewrite to disabled/unwired/not selected/not installed.
6. Architectural boundary — preserve boundary, but replace vague defer language with "outside this boundary because...".
7. Stale drift — correct or remove.
8. Brittle slice reference — remove if adjacent to defer/later/future language and replace with stable capability boundary.

Stable boundary names to prefer over slice numbers:
- Local LLM runtime boundary
- Runtime escalation boundary
- Semantic memory boundary
- Agent runtime boundary
- Realtime conversation/session boundary
- Streaming response boundary
- Tool orchestration boundary
- Voice interaction boundary
- Telephony/channel adapter boundary
- Desktop shell boundary
- Readiness/provisioning boundary
- Hardware acceleration boundary
- Personality policy boundary
- Retrieval/search boundary
- Validation/evidence boundary

Preferred replacement patterns:
- "deferred until later" -> "not implemented in the current boundary; next owner is <stable capability boundary>"
- "deferred to M.1" -> "<capability> is not currently wired/verified; the <stable capability boundary> owns wiring and validation"
- "deferred until Slice N" -> "<capability> is outside the current boundary; ownership belongs to the <stable capability boundary>"
- "future Group M owns X" -> "the <stable capability boundary> owns X"
- "agent behavior deferred" -> "no autonomous agent behavior is claimed; current support is deterministic tools/prompt-envelope reasoning"
- "semantic memory deferred" -> "semantic/vector memory is not implemented; current memory support is episodic retrieval only"
- "remote escalation deferred" -> "remote escalation is not implemented; current runtime policy remains local-first"
- "TODO defer X" -> "TODO introduce X at the <stable capability boundary>; current behavior is <specific limitation>"

Examples:
Bad:
- "llama.cpp is deferred to M.1."
Good:
- "llama.cpp is not currently wired as a verified runtime. The local LLM runtime boundary owns wiring and validation."

Bad:
- "Semantic memory is deferred until a future slice."
Good:
- "Semantic/vector memory is not implemented. Current memory support is episodic retrieval only. The semantic memory boundary owns this capability."

Bad:
- "Agent behavior is deferred to Group N."
Good:
- "No autonomous agent behavior is claimed. The agent runtime boundary owns task decomposition, role handoff, and agent-led execution."

Bad:
- "Streaming is deferred to a later voice slice."
Good:
- "Streaming response is not implemented. Current voice behavior is batch turn execution. The streaming response boundary owns partial output and cancellation behavior."

Hard boundaries:
- Do not change runtime behavior.
- Do not invent capabilities.
- Do not update claims beyond validation evidence.
- Do not rewrite ProjectVision to match current limitations; ProjectVision remains aspirational unless it contains misleading execution language.
- Do not sanitize historical slice docs unless the wording is now stale or actively misleading.
- Do not remove valid out-of-scope statements; rewrite them to be precise.
- Do not preserve slice-name/number references beside deferred language in active guidance docs.
- Do not touch unrelated formatting.

Validation:
Run at minimum:
- git diff --check
- repository-wide search confirming remaining defer/deferred occurrences are intentional
- repository-wide search confirming remaining slice-name/number references near defer/later/future language are intentional or historical
- if any code comments or strings are touched in Python files, run the smallest relevant Python validation required by AGENTS.md

Deliverable:
1. Summary of files changed.
2. Count of defer/deferred occurrences before and after.
3. Count of brittle slice-name/number references removed or rewritten.
4. List of remaining defer/deferred occurrences and reason each remains.
5. List of remaining slice/group/phase references adjacent to defer/later/future wording and reason each remains.
6. Note any capability wording changed from "deferred" to "not implemented", "not wired", "not claimed", "disabled", "outside this boundary", or "owned by <stable boundary>".
7. Validation commands and outcomes.

Stop condition:
Stop after active governing docs and misleading current comments/config wording are cleaned. Do not expand into implementation, roadmap restructuring, or feature work.