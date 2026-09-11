import sys
import io
import argparse
from pathlib import Path

content = Path('scripts/validate_backend.py').read_text('utf-8')

main_logic = '''
    if args.command in ("unit", "ci"):
        started_at = _current_timestamp()
        report_path = VALIDATION_DIR / f"{_timestamp_slug()}-{args.command}_backend.txt"
        
        print(f"JARVISv7 Backend {args.command.upper()} Validation started at {started_at}")
        print(f"Report File: {_relative_report_path(report_path)}")
        print(f"Host Fingerprint: {fingerprint_line}")
        print(f"Command: {args.command}")
        
        # Capture stdout/stderr
        import io
        import sys
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        sys.stdout = stdout_buf
        sys.stderr = stderr_buf
        
        try:
            if args.command == "unit":
                validator_code = _command_unit()
            else:
                validator_code = _command_ci()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
        stdout_str = stdout_buf.getvalue()
        stderr_str = stderr_buf.getvalue()
        
        status_tag = "[PASS]" if validator_code == 0 else "[FAIL]"
        
        report_lines = [
            f"JARVISv7 Backend {args.command.upper()} Validation started at {started_at}",
            f"Report File: {_relative_report_path(report_path)}",
            f"Host Fingerprint: {fingerprint_line}",
            f"Command: {args.command}",
            f"Return Code: {validator_code}",
            "",
            "STDOUT",
            "------",
            stdout_str.strip() if stdout_str.strip() else "<empty>",
            "",
            "STDERR",
            "------",
            stderr_str.strip() if stderr_str.strip() else "<empty>",
            "",
            "VALIDATION SUMMARY",
            f"{status_tag} JARVISv7 backend {args.command} is validated!" if validator_code == 0 else f"{status_tag} JARVISv7 backend {args.command} failed!"
        ]
        
        _write_report_at_path(report_path, "\\n".join(report_lines) + "\\n")
        
        if validator_code == 0:
            print(f"{status_tag} JARVISv7 backend {args.command} is validated!")
        else:
            print(f"{status_tag} JARVISv7 backend {args.command} failed!")
            
        _clean_old_reports()
        return validator_code
'''

# We also need to add _clean_old_reports call to regression
