from pathlib import Path

adr_path = Path("docs/adr/0005-governed-ability-to-act.md")
lines = adr_path.read_text('utf-8').splitlines()

new_lines = []
for line in lines:
    if "Route fully specified operator agent invocation through" in line:
        continue
    new_lines.append(line)

adr_path.write_text("\n".join(new_lines) + "\n", 'utf-8')
