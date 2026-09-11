from pathlib import Path

for md_file in ['docs/QuickStart-linux.md', 'docs/QuickStart-windows.md']:
    path = Path(md_file)
    content = path.read_text('utf-8')
    if 'linux' in md_file:
        content = content.replace('npm --prefix desktop test', 'backend/.venv/bin/python scripts/validate_desktop.py regression')
    else:
        content = content.replace('npm --prefix desktop test', '.\\backend\\.venv\\Scripts\\python scripts\\validate_desktop.py regression')
    path.write_text(content, 'utf-8')
