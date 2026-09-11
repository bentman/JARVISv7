from pathlib import Path

path = Path('backend/tests/unit/core/test_settings.py')
text = path.read_text('utf-8')

text = text.replace('ENV_EXAMPLE_UNIMPLEMENTED_NAMES: set[str] = {', 'ENV_EXAMPLE_UNIMPLEMENTED_NAMES: set[str] = set(')
text = text.replace('}\n\nENV_EXAMPLE_REQUIRED_NAMES', ')\n\nENV_EXAMPLE_REQUIRED_NAMES')

path.write_text(text, 'utf-8')
