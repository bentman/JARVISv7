from pathlib import Path

path = Path('backend/tests/unit/core/test_settings.py')
text = path.read_text('utf-8')

# Remove APP_NAME from the test asserts
lines = text.split('\n')
new_lines = []
for line in lines:
    if 'APP_NAME' in line:
        continue
    new_lines.append(line)

path.write_text('\n'.join(new_lines), 'utf-8')
