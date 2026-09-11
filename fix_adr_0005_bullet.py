from pathlib import Path
import re

adr_path = Path("docs/adr/0005-governed-ability-to-act.md")
content = adr_path.read_text('utf-8')

# The exact text to remove
bullet = "- Route fully specified operator agent invocation through CapabilityService.invoke_operator_capability. POST /agents/invoke still uses the proposal path and can ask for self-approval; preserve agent run tracking, cancellation, and evidence when correcting it. ADR 0007 owns the agent workflow.\n"
content = content.replace(bullet, "")

adr_path.write_text(content, 'utf-8')
