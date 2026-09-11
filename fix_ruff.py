from pathlib import Path

sessions_path = Path('backend/app/actions/sessions.py')
lines = sessions_path.read_text('utf-8').split('\n')

for i, line in enumerate(lines):
    if line.startswith('class SessionResourceDied(Exception):'):
        lines[i] = 'class SessionResourceDied(Exception):  # noqa: N818'
    elif line.startswith('class SessionCallOutcomeUnknown(Exception):'):
        lines[i] = 'class SessionCallOutcomeUnknown(Exception):  # noqa: N818'

sessions_path.write_text('\n'.join(lines), 'utf-8')
