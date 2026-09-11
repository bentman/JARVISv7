import subprocess
import sys
from pathlib import Path

path = Path('scripts/validate_backend.py')
content = path.read_text('utf-8')

import_time = "from datetime import UTC, datetime, timedelta"
content = content.replace("from datetime import UTC, datetime", import_time)

cleanup_func = '''
def _clean_old_reports() -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    if not VALIDATION_DIR.exists():
        return
    for report_file in VALIDATION_DIR.glob("*-*.txt"):
        try:
            # Filename starts with 14 char timestamp %Y%m%d%H%M%S
            ts_str = report_file.name[:14]
            file_time = datetime.strptime(ts_str, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            if file_time < cutoff:
                report_file.unlink()
        except ValueError:
            pass
'''
if "def _clean_old_reports" not in content:
    # insert before _current_timestamp
    content = content.replace("def _current_timestamp() -> str:", cleanup_func + "\ndef _current_timestamp() -> str:")

# Now we need to modify _run_pytest and _run_quality_tool to capture output if we want, OR
# We can just change _command_unit and _command_ci to use subprocess directly.
# Wait, it's easier to modify main() to just intercept "unit" and "ci" like "regression" does,
# or we can modify the commands.
