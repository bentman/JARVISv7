from pathlib import Path

adr_path = Path("docs/adr/0005-governed-ability-to-act.md")
content = adr_path.read_text('utf-8')

# Update class names
content = content.replace("SessionCallOutcomeUnknown", "SessionCallOutcomeUnknownError")

# Update implementation summary
old_summary = "This ADR is partially implemented. Shared governance, execution boundaries, durable evidence, and session management are built. Agent operator-invocation authorization and the action audit presentation remain incomplete."
new_summary = "This ADR is partially implemented. Shared governance, execution boundaries, durable evidence, session management, and agent operator-invocation authorization are built. The action audit presentation remains incomplete."
content = content.replace(old_summary, new_summary)

# Remove the follow up bullet for agent operator invocation
follow_up_lines = []
skip = False
for line in content.split('\n'):
    if line.startswith("- Route fully specified operator agent invocation through CapabilityService.invoke_operator_capability"):
        continue
    follow_up_lines.append(line)

adr_path.write_text('\n'.join(follow_up_lines), 'utf-8')
