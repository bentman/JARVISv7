import os
import re
from pathlib import Path

repo = Path("E:/WORK/CODE/REPO/JARVISv7/backend")
pattern = re.compile(r'SessionResourceDied|SessionCallOutcomeUnknown')

for root, _, files in os.walk(repo):
    for f in files:
        if f.endswith('.py'):
            path = Path(root) / f
            text = path.read_text('utf-8')
            if pattern.search(text):
                print(f"Found in {path.relative_to(repo)}")
