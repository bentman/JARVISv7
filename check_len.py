import re
from pathlib import Path

content = Path('scripts/validate_backend.py').read_text('utf-8')

# Let's see what main looks like right now
print(len(content))
