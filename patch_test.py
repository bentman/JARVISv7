import re
from pathlib import Path

path = Path('backend/tests/unit/scripts/test_validate_backend_script.py')
content = path.read_text('utf-8')

patch_context_func = '''def _patch_context(monkeypatch, tmp_path=None) -> None:
    profile = ProfileEvidence(id="default", path=Path("/profile.json"), metadata={})
    flags = FlagEvidence(desktop_interactive=False, desktop_window=False)
    report = ContextReport(profile=profile, flags=flags)
    extras = HardwareExtras(cpu_base=True, x64_base=True, arm64_base=False, gpu_nvidia_cuda=False, gpu_amd_rocm=False, gpu_qualcomm_qnn=False, dev=False)
    preflight = PreflightSummary(tokens=[], dll_discovery_log=[], probe_errors=[])
    context = InvocationContext(host_arch="amd64", python_version="3.12", runtime_mode="test", overrides={}, report=report, extras=extras, preflight=preflight)
    monkeypatch.setattr(validate_backend, "_load_context", lambda: context)
    monkeypatch.setattr(validate_backend, "selected_path_readiness_summary", lambda _: "ready")
    if tmp_path:
        monkeypatch.setattr(validate_backend, "VALIDATION_DIR", tmp_path)
'''
# We need to find def _patch_context(monkeypatch) -> None:
content = re.sub(r'def _patch_context.*?monkeypatch.setattr.*?lambda _: "ready"\)', patch_context_func.strip(), content, flags=re.DOTALL)

# And then we need to update test signatures to take tmp_path and pass it to _patch_context.
test_replacements = [
    ("def test_unit_subcommand_invokes_pytest_on_unit_dir(monkeypatch, capsys) -> None:", "def test_unit_subcommand_invokes_pytest_on_unit_dir(monkeypatch, capsys, tmp_path) -> None:"),
    ("_patch_context(monkeypatch)", "_patch_context(monkeypatch, tmp_path)")
]

for old, new in test_replacements:
    content = content.replace(old, new)

# wait, _patch_context(monkeypatch) is called in multiple tests!
# Let's just patch VALIDATION_DIR in _patch_context directly using monkeypatch and a fake path? No, tmp_path fixture is better.
