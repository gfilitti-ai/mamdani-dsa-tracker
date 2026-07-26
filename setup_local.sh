#!/bin/bash
# One-time local setup: create the venv and install dependencies.
set -euo pipefail
DIR="/Users/filitti/Downloads/mamdani-dsa-tracker"
cd "$DIR"

python3 -m venv venv
./venv/bin/pip install --upgrade pip >/dev/null
./venv/bin/pip install -r requirements.txt
echo "Done. Now: echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env  &&  ./run.sh"
