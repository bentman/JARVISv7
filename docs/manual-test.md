cd D:\WORK\CODE\GitHub\bentman\Repositories\JARVISv7

Remove-Item -Recurse -Force backend\.venv -ErrorAction SilentlyContinue

$env:TEMP = "$PWD\cache\temp"
$env:TMP  = "$PWD\cache\temp"
$env:TMPDIR = "$PWD\cache\temp"
$env:PIP_CACHE_DIR = "$PWD\cache\pip"
New-Item -ItemType Directory -Force $env:TEMP, $env:PIP_CACHE_DIR | Out-Null

py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python -m ensurepip --upgrade
backend\.venv\Scripts\python -m pip install --upgrade pip setuptools wheel

backend\.venv\Scripts\python scripts\provision.py install
backend\.venv\Scripts\python scripts\validate_backend.py profile
backend\.venv\Scripts\python scripts\validate_backend.py regression