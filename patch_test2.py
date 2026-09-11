import re
from pathlib import Path

path = Path('backend/tests/unit/scripts/test_validate_backend_script.py')
content = path.read_text('utf-8')

content = content.replace("def _patch_context(monkeypatch) -> None:", "def _patch_context(monkeypatch, tmp_path=None) -> None:")
content = content.replace(
    'monkeypatch.setattr(validate_backend, "selected_path_readiness_summary", lambda _: "ready")',
    'monkeypatch.setattr(validate_backend, "selected_path_readiness_summary", lambda _: "ready")\n    if tmp_path:\n        monkeypatch.setattr(validate_backend, "VALIDATION_DIR", tmp_path)'
)

# For any test that calls _patch_context(monkeypatch) WITHOUT tmp_path, we need to add tmp_path to its signature if it doesn't have it, and pass it.
# Actually, only test_unit_subcommand_invokes_pytest_on_unit_dir, test_ci_subcommand_runs_quality_and_test_commands_in_order, test_ci_subcommand_propagates_quality_failure write to VALIDATION_DIR!
# What about test_regression_report_helpers_emit_structured_rows? That doesn't run main().
# What about test_exit_codes_map_documented_states_correctly? That calls main(["unit"]) and main(["all"])!
# I will just replace all _patch_context(monkeypatch) with _patch_context(monkeypatch, tmp_path) and ensure 	mp_path is in the test arguments.

def fix_test(match):
    sig = match.group(1)
    body = match.group(2)
    if "tmp_path" not in sig:
        if ")" in sig:
            sig = sig.replace(")", ", tmp_path)")
    body = body.replace("_patch_context(monkeypatch)", "_patch_context(monkeypatch, tmp_path)")
    return f"{sig}:\n{body}"

content = re.sub(r'(def test_\w+\(.*?\)):(.*?(?=\n\n|$))', fix_test, content, flags=re.DOTALL)

path.write_text(content, 'utf-8')
