import os
from pathlib import Path

repo = Path("E:/WORK/CODE/REPO/JARVISv7/backend")
replacements = {
    "SessionResourceDied": "SessionResourceDiedError",
    "SessionCallOutcomeUnknown": "SessionCallOutcomeUnknownError"
}

for root, _, files in os.walk(repo):
    for f in files:
        if f.endswith('.py'):
            path = Path(root) / f
            try:
                text = path.read_text('utf-8')
            except UnicodeDecodeError:
                continue
                
            new_text = text
            for old, new in replacements.items():
                new_text = new_text.replace(old, new)
            
            # Remove the noqa tags we added earlier
            new_text = new_text.replace(f"class SessionResourceDiedError(Exception):  # noqa: N818", f"class SessionResourceDiedError(Exception):")
            new_text = new_text.replace(f"class SessionCallOutcomeUnknownError(Exception):  # noqa: N818", f"class SessionCallOutcomeUnknownError(Exception):")
            
            if new_text != text:
                path.write_text(new_text, 'utf-8')
                print(f"Updated {path.relative_to(repo)}")
