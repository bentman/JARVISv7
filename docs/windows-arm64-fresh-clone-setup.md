# Windows ARM64 Fresh-Clone Setup

## Purpose

Initialize a fresh Windows ARM64 clone to a bootstrap-ready repository state.

## Fresh-clone expectations

- `backend/.venv` is local to your machine and is expected to be absent in a fresh clone.
- `models/*` may be absent in a fresh clone; bootstrap may acquire repo-managed model artifacts.
- Setup is governed by repository scripts and the repo-root `pyproject.toml`.
- `backend/requirements.txt` is a generated lockfile and must not be hand-edited.
- Using repo-local `cache/temp` and `cache/pip` helps reduce ARM64 shell/cache permission issues.

## PowerShell setup commands

```powershell
# Windows PowerShell, run from repo root
Set-Location <REPO_ROOT_PATH>

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:TEMP = "$PWD\cache\temp"
$env:TMP = "$PWD\cache\temp"
$env:TMPDIR = "$PWD\cache\temp"
$env:PIP_CACHE_DIR = "$PWD\cache\pip"
New-Item -ItemType Directory -Force $env:TEMP, $env:PIP_CACHE_DIR | Out-Null

$pyVersionRaw = (py --version)                         # e.g., "Python 3.13.13"
$pyVersionMM = (($pyVersionRaw -split '\s+')[-1] -split '\.')[0..1] -join '.'
py -$pyVersionMM -m venv backend\.venv
backend\.venv\Scripts\python -m pip install --upgrade pip
backend\.venv\Scripts\python scripts\provision.py install
backend\.venv\Scripts\python scripts\bootstrap.py
backend\.venv\Scripts\python scripts\ensure_models.py --verify-only
```

## Desktop launch from a fresh clone

Run from repo root:

```powershell
npm --prefix desktop install
npm --prefix desktop run dev
```

Do not install Tauri globally. Use the repo-local desktop dependencies.

## Missing-module recovery

If `scripts/bootstrap.py` fails before checkpoint 2 with a missing Python module, do not install modules by hand.

Refresh to the latest repository state and rerun bootstrap. If the same error persists, run:

```powershell
backend\.venv\Scripts\python scripts\provision.py install
backend\.venv\Scripts\python scripts\bootstrap.py
backend\.venv\Scripts\python scripts\ensure_models.py --verify-only
```

## Stop rule

If `scripts/bootstrap.py` fails, stop at the failing checkpoint and fix that prerequisite before continuing.
