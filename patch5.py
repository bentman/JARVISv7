from pathlib import Path

path = Path('backend/tests/unit/scripts/test_validate_backend_script.py')
content = path.read_text('utf-8')

content = content.replace("test_runtime_subcommand_accepts_families_and_devices_filters(monkeypatch, capsys)", "test_runtime_subcommand_accepts_families_and_devices_filters(monkeypatch, capsys, tmp_path)")

path.write_text(content, 'utf-8')
