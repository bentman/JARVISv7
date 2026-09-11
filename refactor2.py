import re
from pathlib import Path

path = Path('scripts/validate_backend.py')
content = path.read_text('utf-8')

# Add timedelta to imports
content = content.replace("from datetime import UTC, datetime", "from datetime import UTC, datetime, timedelta")

# Add _clean_old_reports function
cleanup_func = '''
def _clean_old_reports() -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    if not VALIDATION_DIR.exists():
        return
    for report_file in VALIDATION_DIR.glob("*-*.txt"):
        try:
            ts_str = report_file.name[:14]
            file_time = datetime.strptime(ts_str, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            if file_time < cutoff:
                report_file.unlink()
        except ValueError:
            pass
'''
content = content.replace("def _current_timestamp() -> str:", cleanup_func + "\ndef _current_timestamp() -> str:")

# Modify _run_pytest and _run_quality_tool to accept an optional log_file (io.TextIOBase)
content = content.replace(
    "def _run_pytest(\n    targets: list[str], marker_expr: str | None = None, keyword_expr: str | None = None,\n) -> int:",
    "def _run_pytest(\n    targets: list[str], marker_expr: str | None = None, keyword_expr: str | None = None, log_file=None\n) -> int:"
)
content = content.replace(
    "completed = subprocess.run(command, cwd=APP_REPO_ROOT, check=False)",
    "completed = subprocess.run(command, cwd=APP_REPO_ROOT, check=False, stdout=log_file, stderr=subprocess.STDOUT if log_file else None)"
)

content = content.replace(
    "def _run_quality_tool(module: str, arguments: list[str]) -> int:",
    "def _run_quality_tool(module: str, arguments: list[str], log_file=None) -> int:"
)
content = content.replace(
    "completed = subprocess.run(\n        [sys.executable, \"-m\", module, *arguments],\n        cwd=APP_REPO_ROOT,\n        check=False,\n    )",
    "completed = subprocess.run(\n        [sys.executable, \"-m\", module, *arguments],\n        cwd=APP_REPO_ROOT,\n        check=False,\n        stdout=log_file,\n        stderr=subprocess.STDOUT if log_file else None,\n    )"
)

# Modify _command_unit and _command_ci to accept log_file
content = content.replace(
    "def _command_unit() -> int:\n    return _run_pytest([\"backend/tests/unit\"])",
    "def _command_unit(log_file=None) -> int:\n    return _run_pytest([\"backend/tests/unit\"], log_file=log_file)"
)

ci_orig = '''def _command_ci() -> int:
    marker_expr = "not live"
    return _combine_codes(
        [
            _run_quality_tool("ruff", ["check", "backend", "scripts"]),
            _run_quality_tool("mypy", ["backend/app"]),
            _run_pytest(["backend/tests/unit"], marker_expr=marker_expr),
            _run_pytest(["backend/tests/integration"], marker_expr=marker_expr),
            _run_pytest(_regression_targets(), marker_expr=marker_expr),
        ]
    )'''

ci_new = '''def _command_ci(log_file=None) -> int:
    marker_expr = "not live"
    return _combine_codes(
        [
            _run_quality_tool("ruff", ["check", "backend", "scripts"], log_file=log_file),
            _run_quality_tool("mypy", ["backend/app"], log_file=log_file),
            _run_pytest(["backend/tests/unit"], marker_expr=marker_expr, log_file=log_file),
            _run_pytest(["backend/tests/integration"], marker_expr=marker_expr, log_file=log_file),
            _run_pytest(_regression_targets(), marker_expr=marker_expr, log_file=log_file),
        ]
    )'''
content = content.replace(ci_orig, ci_new)

# Modify main to handle unit and ci reports
main_orig = '''    if args.command == "unit":
        return _command_unit()
    if args.command == "integration":'''

main_new = '''    if args.command in ("unit", "ci"):
        started_at = _current_timestamp()
        report_path = VALIDATION_DIR / f"{_timestamp_slug()}-{args.command}_backend.txt"
        
        print(f"JARVISv7 Backend {args.command.upper()} Validation started at {started_at}")
        print(f"Report File: {_relative_report_path(report_path)}")
        print(f"Host Fingerprint: {fingerprint_line}")
        print(f"Command: {args.command}")
        
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"JARVISv7 Backend {args.command.upper()} Validation started at {started_at}\\n")
            log_file.write(f"Report File: {_relative_report_path(report_path)}\\n")
            log_file.write(f"Host Fingerprint: {fingerprint_line}\\n")
            log_file.write(f"Command: {args.command}\\n\\n")
            log_file.write("STDOUT/STDERR\\n------\\n")
            
            if args.command == "unit":
                validator_code = _command_unit(log_file=log_file)
            else:
                validator_code = _command_ci(log_file=log_file)
                
            log_file.write("\\nVALIDATION SUMMARY\\n")
            status_tag = "[PASS]" if validator_code == 0 else "[FAIL]"
            log_file.write(f"{status_tag} JARVISv7 backend {args.command} is validated!\\n" if validator_code == 0 else f"{status_tag} JARVISv7 backend {args.command} failed!\\n")
            
        if validator_code == 0:
            print(f"\\n[PASS] JARVISv7 backend {args.command} is validated!")
        else:
            print(f"\\n[FAIL] JARVISv7 backend {args.command} failed!")
            
        _clean_old_reports()
        return validator_code

    if args.command == "integration":'''
content = content.replace(main_orig, main_new)

# Add _clean_old_reports() call to regression
regression_end = '''        if validator_code == 0:
            print("[PASS] JARVISv7 backend regression is validated!")
        else:
            print("[FAIL] JARVISv7 backend regression failed!")

        return validator_code'''
regression_end_new = '''        if validator_code == 0:
            print("[PASS] JARVISv7 backend regression is validated!")
        else:
            print("[FAIL] JARVISv7 backend regression failed!")

        _clean_old_reports()
        return validator_code'''
content = content.replace(regression_end, regression_end_new)

path.write_text(content, 'utf-8')
print("Refactored successfully")
