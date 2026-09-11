import ast
import os
from collections import defaultdict
from pathlib import Path

repo_root = Path("E:/WORK/CODE/REPO/JARVISv7/backend/app")
tests_root = Path("E:/WORK/CODE/REPO/JARVISv7/backend/tests")

defined_methods = {}  # (class_name, method_name) -> filepath
called_names = set()

# First pass: find definitions
for root, dirs, files in os.walk(repo_root):
    for f in files:
        if not f.endswith(".py"): continue
        path = Path(root) / f
        try:
            tree = ast.parse(path.read_text('utf-8'))
        except SyntaxError:
            continue
            
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        # skip dunder methods
                        if child.name.startswith('__') and child.name.endswith('__'):
                            continue
                        # skip methods with decorators (fastapi endpoints, pydantic validators)
                        if any(isinstance(dec, ast.Name) and dec.id in ('model_validator', 'field_validator', 'computed_field', 'property') for dec in child.decorator_list):
                            continue
                        if any(isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id in ('model_validator', 'field_validator', 'router.get', 'router.post', 'router.delete', 'router.put') for dec in child.decorator_list):
                            continue
                        if any(isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in ('get', 'post', 'delete', 'put') for dec in child.decorator_list):
                            continue
                            
                        defined_methods[(node.name, child.name)] = path

# Second pass: find calls anywhere in app or tests
for search_root in (repo_root, tests_root):
    for root, dirs, files in os.walk(search_root):
        for f in files:
            if not f.endswith(".py"): continue
            path = Path(root) / f
            try:
                tree = ast.parse(path.read_text('utf-8'))
            except SyntaxError:
                continue
                
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        called_names.add(node.func.attr)
                    elif isinstance(node.func, ast.Name):
                        called_names.add(node.func.id)

# Report methods that are never called
print("Potentially Uncalled Methods:")
for (cls, method), path in defined_methods.items():
    if method not in called_names:
        print(f"{cls}.{method} in {path.relative_to(repo_root.parent)}")
