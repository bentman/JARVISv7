from pathlib import Path

path = Path('backend/tests/unit/core/test_settings.py')
text = path.read_text('utf-8')

# Search for the block starting with RETIRED_SETTING_NAMES and replace up to ENV_EXAMPLE_REQUIRED_NAMES
new_text = []
skip = False
for line in text.split('\n'):
    if line.startswith('RETIRED_SETTING_NAMES = {'):
        skip = True
        new_text.append('RETIRED_SETTING_NAMES = {')
        new_text.append('    "CONFIG_PATH",')
        new_text.append('    "DATA_PATH",')
        new_text.append('    "MODEL_PATH",')
        new_text.append('    "STT_MODELS",')
        new_text.append('    "TTS_MODELS",')
        new_text.append('    "WAKE_MODEL",')
        new_text.append('}')
        new_text.append('')
        new_text.append('ENV_EXAMPLE_UNIMPLEMENTED_NAMES: set[str] = set()')
        new_text.append('')
    elif line.startswith('ENV_EXAMPLE_REQUIRED_NAMES: set[str] = {'):
        skip = False
    
    if not skip:
        new_text.append(line)

path.write_text('\n'.join(new_text), 'utf-8')
