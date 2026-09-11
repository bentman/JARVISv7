from pathlib import Path

path = Path('README.md')
content = path.read_text('utf-8')

if '* automated validation logs' not in content:
    content = content.replace('* desktop resident voice proof paths', '* desktop resident voice proof paths\n* automated validation logs and garbage collection for repeatable proof')

path.write_text(content, 'utf-8')
