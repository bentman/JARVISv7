from pathlib import Path

# Fix Linux QuickStart
linux_path = Path('docs/QuickStart-linux.md')
linux_content = linux_path.read_text('utf-8')
linux_content = linux_content.replace('backend/.venv/bin/python scripts/validate_desktop.py regression', 'npm --prefix desktop test')
linux_path.write_text(linux_content, 'utf-8')

# Fix Windows QuickStart
win_path = Path('docs/QuickStart-windows.md')
win_content = win_path.read_text('utf-8')
win_content = win_content.replace('.\\backend\\.venv\\Scripts\\python scripts\\validate_desktop.py regression', 'npm --prefix desktop test')
win_path.write_text(win_content, 'utf-8')

print("Reverted quickstarts.")
