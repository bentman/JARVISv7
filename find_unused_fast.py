import ast
import re
from pathlib import Path
from collections import Counter

app_dir = Path("backend/app")
defined = {}

for py_file in app_dir.rglob("*.py"):
    try:
        tree = ast.parse(py_file.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    defined[node.name] = py_file
    except Exception:
        pass

print(f"Found {len(defined)} definitions.")

word_counts = Counter()
for ext in ["*.py", "*.js", "*.rs", "*.md", "*.html"]:
    for f in Path(".").rglob(ext):
        if "node_modules" in str(f) or ".venv" in str(f) or ".git" in str(f) or "dist" in str(f):
            continue
        try:
            content = f.read_text("utf-8", errors="ignore")
            # Find all words
            words = re.findall(r'[a-zA-Z_]\w*', content)
            word_counts.update(words)
        except Exception:
            pass

unused = []
for name, path in defined.items():
    if word_counts[name] <= 1:
        unused.append(f"{name} in {path}")

print("Potentially Unused Definitions:")
for u in unused:
    print(u)
