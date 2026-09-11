from pathlib import Path
path = Path('backend/tests/unit/scripts/test_validate_backend_script.py')
content = path.read_text('utf-8')

# Find def _patch_context
old = 'def _patch_context(monkeypatch, tmp_path=None) -> None:'
new = '''def _patch_context(monkeypatch, tmp_path=None) -> None:
    monkeypatch.setattr(validate_backend, "_relative_report_path", lambda path: str(path))'''
content = content.replace(old, new)

path.write_text(content, 'utf-8')
