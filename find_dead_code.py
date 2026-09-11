import ast
from pathlib import Path
import re

app_dir = Path("backend/app")
defined = set()

for py_file in app_dir.rglob("*.py"):
    try:
        tree = ast.parse(py_file.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                if not node.name.startswith("_"):
                    defined.add(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    defined.add(node.name)
    except Exception:
        pass

# Now scan all codebase to count occurrences
code_text = ""
for py_file in Path(".").rglob("*.py"):
    code_text += py_file.read_text("utf-8") + "\n"
for js_file in Path(".").rglob("*.js"):
    code_text += js_file.read_text("utf-8") + "\n"
for rs_file in Path(".").rglob("*.rs"):
    code_text += rs_file.read_text("utf-8") + "\n"

unused = []
for name in defined:
    # count matches of the name as a word boundary
    matches = len(re.findall(r'\b' + re.escape(name) + r'\b', code_text))
    if matches <= 1:
        unused.append(name)

print("Possibly Unused:", unused)
