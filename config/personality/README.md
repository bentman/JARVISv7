# Personality profiles

This directory contains selectable assistant personality profiles. Each profile is a YAML file loaded by the backend personality loader and selected through the personality API.

## Profile shape

Each profile defines:

- `profile_id`: safe lowercase id used by the API and desktop selector.
- `display_name`: user-facing profile name.
- `description`: short API and desktop summary.
- `locale`: response locale hint.
- `system`: primary assistant behavior text.
- `style`: word limit, response structure, and direct do/avoid rules.
- `traits`: light behavior controls for warmth, assertiveness, detail, and humor.
- `examples`: short user/assistant examples for style anchoring.
- `generation`: runtime generation defaults.
- `enabled`: profile availability flag.

## Traits

Traits are functional. `backend/app/personality/policy.py` maps trait values into the compiled `Behavior traits:` section sent with the selected profile.

Supported values:

- `warmth`: `none`, `low`, `medium`, `high`, `strong`
- `assertiveness`: `none`, `low`, `medium`, `high`, `strong`
- `detail`: `none`, `low`, `medium`, `high`, `strong`
- `humor`: `none`, `light`, `medium`, `high`, `dry`

Use `system` and `style` for hard response requirements. Use `traits` for light personality shaping. Humor level belongs in `traits.humor`.

## Editing guidance

Keep examples general-assistant focused and short. Keep `style.max_words_default` aligned with `generation.max_tokens`. Update tests when profile shape, trait behavior, examples, or generation defaults change.

## Validation

Focused personality validation:

```powershell
backend\.venv\Scripts\python -m pytest backend\tests\unit\personality -q
```

Runtime payload validation when compiled profile text or generation defaults change:

```powershell
backend\.venv\Scripts\python -m pytest backend\tests\unit\runtimes\llm\test_llm_runtime.py -q
```
