import re
from pathlib import Path

def remove_method(file_path: str, method_name: str):
    p = Path(file_path)
    lines = p.read_text('utf-8').splitlines()
    new_lines = []
    skip = False
    indent = ""
    for line in lines:
        match = re.match(r'^(\s*)def ' + method_name + r'\(', line)
        if match:
            skip = True
            indent = match.group(1)
            continue
        if skip:
            # If it's a blank line or starts with more indent, we skip
            # If it starts with same or less indent and has code, stop skipping
            if line.strip() == "":
                continue
            if line.startswith(indent + " ") or line.startswith(indent + "\t"):
                continue
            skip = False
        if not skip:
            new_lines.append(line)
    p.write_text('\n'.join(new_lines) + '\n', 'utf-8')
    print(f"Removed {method_name} from {file_path}")

remove_method("backend/app/services/session_service.py", "replace_engine")
remove_method("backend/app/cognition/search_policy.py", "validate_queries")
remove_method("backend/app/artifacts/turn_artifact.py", "agent_evidence")
remove_method("backend/app/services/daemon_registry.py", "public_status")
