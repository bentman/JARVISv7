from pathlib import Path

walkthrough_path = Path('C:/Users/bentl/.gemini/antigravity/brain/33e8d1a9-d1c2-4c8e-9460-ee66b12abc19/walkthrough.md')
content = walkthrough_path.read_text('utf-8')

new_content = """
## Round 4: Gap Documentation (Surgical Alignment)

- **ADR 0006 (`0006-ways-to-extend-assistant-ability-to-act.md`):** Surgically updated the follow-up section to explicitly mandate validation of native desktop recovery for session failures (`outcome_unknown`), ensuring the exception naming cleanups do not mask the remaining UI integration gap.
- **ADR 0001 (`0001-know-the-machine.md`):** Added follow-up requirements to (1) audit all active environment variables against actual usage (addressing the config drift exposed by `APP_NAME`), and (2) stabilize environment-sensitive timing mocks in runtime startup tests (acknowledging the flaky `test_local_llm_startup.py` mitigation).
- **ADR 0007 (`0007-extend-assistant-when-stable.md`):** Confirmed the follow-up section already correctly tracks the fundamental absence of ACP v2 conformance, `router_selected`/`handoff` wiring, and Agent adapters.
"""

if "## Round 4" not in content:
    content += "\n" + new_content
    walkthrough_path.write_text(content, 'utf-8')
