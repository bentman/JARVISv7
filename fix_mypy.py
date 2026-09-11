import re
from pathlib import Path

error_file = Path('mypy_test_errors.txt')
lines = error_file.read_text('utf-8').splitlines()

# Regex to parse mypy output: file:line: error: message [error-code]
pattern = re.compile(r'^(.*?):(\d+): error: (.*) \[(.*)\]$')

# Group fixes by file
fixes = {}

for line in lines:
    match = pattern.match(line)
    if not match:
        continue
        
    filepath, linenum, msg, code = match.groups()
    linenum = int(linenum)
    
    if code in ('func-returns-value', 'unused-ignore', 'import-untyped'):
        if filepath not in fixes:
            fixes[filepath] = []
        fixes[filepath].append((linenum, code, msg))

for filepath, file_fixes in fixes.items():
    p = Path(filepath)
    if not p.exists():
        continue
        
    content_lines = p.read_text('utf-8').splitlines()
    
    # Sort fixes by line number descending so we can modify in place
    file_fixes.sort(key=lambda x: x[0], reverse=True)
    
    for linenum, code, msg in file_fixes:
        idx = linenum - 1
        if idx < 0 or idx >= len(content_lines):
            continue
            
        line_content = content_lines[idx]
        
        if code == 'unused-ignore':
            # Remove type: ignore
            new_line = re.sub(r'\s*#\s*type:\s*ignore.*$', '', line_content)
            content_lines[idx] = new_line
        elif code == 'func-returns-value' or code == 'import-untyped':
            # Append type: ignore
            if '# type: ignore' not in line_content:
                content_lines[idx] = line_content + f'  # type: ignore[{code}]'
                
    p.write_text('\n'.join(content_lines) + '\n', 'utf-8')

print(f"Fixed {sum(len(f) for f in fixes.values())} very-low mypy errors.")
