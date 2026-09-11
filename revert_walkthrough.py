from pathlib import Path

walkthrough_path = Path('C:/Users/bentl/.gemini/antigravity/brain/33e8d1a9-d1c2-4c8e-9460-ee66b12abc19/walkthrough.md')
content = walkthrough_path.read_text('utf-8')

# Remove the ADR 0001 line from the walkthrough
new_lines = []
for line in content.splitlines():
    if "**ADR 0001" in line:
        continue
    new_lines.append(line)

walkthrough_path.write_text("\n".join(new_lines), 'utf-8')
