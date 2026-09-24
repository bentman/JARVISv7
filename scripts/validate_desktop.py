import argparse
import subprocess
import sys

# Add scripts directory to path to import helpers
import validate_backend

COMMANDS = (
    ["npm", "--prefix", "desktop", "test"],
    ["cargo", "test", "--manifest-path", "desktop/src-tauri/Cargo.toml"],
)


def _run(command: list[str]) -> tuple[int, str, str]:
    try:
        # Use shell=True on Windows for npm
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=sys.platform == "win32",
            cwd=str(validate_backend.APP_REPO_ROOT)
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", f"{command[0]} not found"

def _command_regression() -> int:
    started_at = validate_backend._current_timestamp()
    timestamp_slug = validate_backend._timestamp_slug()
    report_path = validate_backend.VALIDATION_DIR / f"{timestamp_slug}-regression_desktop.txt"

    context = validate_backend._load_context()
    fingerprint_line = validate_backend._capture_host_fingerprint(context.profile, context.extras, readiness=validate_backend.selected_path_readiness_summary(context))

    print(f"JARVISv7 Desktop Regression Validation started at {started_at}")
    print(f"Report File: {validate_backend._relative_report_path(report_path)}")
    print(f"Host Fingerprint: {fingerprint_line}")
    report_lines = [
        f"JARVISv7 Desktop Regression Validation started at {started_at}",
        f"Report File: {validate_backend._relative_report_path(report_path)}",
        f"Host Fingerprint: {fingerprint_line}",
    ]
    return_code = 0
    for command in COMMANDS:
        print(f"Command: {' '.join(command)}")
        code, stdout, stderr = _run(command)
        return_code = return_code or code
        report_lines += [
            f"Command: {' '.join(command)}",
            f"Return Code: {code}",
            "",
            "STDOUT",
            "------",
            stdout.strip() if stdout.strip() else "<empty>",
            "",
            "STDERR",
            "------",
            stderr.strip() if stderr.strip() else "<empty>",
            "",
        ]

    status_tag = "[PASS]" if return_code == 0 else "[FAIL]"
    status_msg = "is validated!" if return_code == 0 else "failed!"

    report_lines += [
        "VALIDATION SUMMARY",
        f"{status_tag} JARVISv7 desktop regression {status_msg}"
    ]

    report_content = "\n".join(report_lines) + "\n"
    validate_backend._write_report_at_path(report_path, report_content)

    if return_code == 0:
        print(f"{status_tag} JARVISv7 desktop regression is validated!")
    else:
        print(f"{status_tag} JARVISv7 desktop regression failed!")

    return return_code

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate JARVISv7 desktop codebase")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("regression")

    args = parser.parse_args()

    if args.command == "regression":
        return _command_regression()

    return 1

if __name__ == "__main__":
    sys.exit(main())
