import re
from pathlib import Path

env_example = Path('.env.example').read_text('utf-8')
settings = Path('backend/app/core/settings.py').read_text('utf-8')

env_vars = set(re.findall(r'^([A-Z0-9_]+)=', env_example, re.MULTILINE))
settings_vars = set(re.findall(r'([A-Z0-9_]+) = Field\(', settings))

print("In .env.example but not in settings.py:")
for v in env_vars - settings_vars:
    print(v)

print("\nIn settings.py but not in .env.example:")
for v in settings_vars - env_vars:
    print(v)
