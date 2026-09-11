from pathlib import Path

path = Path('backend/tests/unit/scripts/test_validate_backend_script.py')
content = path.read_text('utf-8')

# 1. Update _patch_context definition
old_patch = 'def _patch_context(monkeypatch) -> None:'
new_patch = '''def _patch_context(monkeypatch, tmp_path=None) -> None:
    if tmp_path:
        monkeypatch.setattr(validate_backend, "VALIDATION_DIR", tmp_path)'''
content = content.replace(old_patch, new_patch)

# 2. Add tmp_path to tests that use _patch_context
def replace_test_sig(test_name, old_args, new_args):
    global content
    content = content.replace(f"def {test_name}({old_args}) -> None:", f"def {test_name}({new_args}) -> None:")

replace_test_sig("test_profile_subcommand_prints_fingerprint_first_line", "monkeypatch, capsys", "monkeypatch, capsys, tmp_path")
replace_test_sig("test_unit_subcommand_invokes_pytest_on_unit_dir", "monkeypatch, capsys", "monkeypatch, capsys, tmp_path")
replace_test_sig("test_ci_subcommand_runs_quality_and_test_commands_in_order", "monkeypatch, capsys", "monkeypatch, capsys, tmp_path")
replace_test_sig("test_ci_subcommand_propagates_quality_failure", "monkeypatch, capsys", "monkeypatch, capsys, tmp_path")
replace_test_sig("test_exit_codes_map_documented_states_correctly", "monkeypatch", "monkeypatch, tmp_path")

content = content.replace("_patch_context(monkeypatch)", "_patch_context(monkeypatch, tmp_path)")

path.write_text(content, 'utf-8')
