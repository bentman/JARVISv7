import re
from pathlib import Path

path = Path('docs/OperationsGuide.md')
content = path.read_text('utf-8')

content = content.replace(
    'backend/.venv/bin/python scripts/validate_backend.py ci\n.\\backend\\.venv\\Scripts\\python scripts\\validate_desktop.py regression',
    'backend/.venv/bin/python scripts/validate_backend.py ci\nbackend/.venv/bin/python scripts/validate_desktop.py regression'
)

log_note = '\nValidation reports for unit, ci, and regression (for both backend and desktop) are written to reports/validation/ and automatically cleaned up after 30 days.\n'
if 'Validation reports' not in content:
    content = content.replace('Repository validation:', log_note + '\nRepository validation:')

path.write_text(content, 'utf-8')
