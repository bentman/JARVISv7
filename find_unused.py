import ast
from pathlib import Path
import re

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

code_text = ""
for ext in ["*.py", "*.js", "*.rs", "*.md", "*.html"]:
    for f in Path(".").rglob(ext):
        if "node_modules" in str(f) or ".venv" in str(f):
            continue
        code_text += f.read_text("utf-8", errors="ignore") + "\n"

unused = []
for name, path in defined.items():
    # Find all occurrences of the word in the entire codebase
    matches = re.findall(r'\b' + re.escape(name) + r'\b', code_text)
    if len(matches) <= 1:
        unused.append(f"{name} in {path}")

print("Potentially Unused Definitions:")
for u in unused:
    print(u)
