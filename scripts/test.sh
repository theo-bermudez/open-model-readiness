#!/bin/sh
# The project's one test command: the full unit suite, then the secret scan over the whole tree.
# Fails (non-zero) if either fails. Run from anywhere:  scripts/test.sh
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
"$PY" -m unittest discover -s tests -t .
"$PY" scripts/secret_scan.py --tree
