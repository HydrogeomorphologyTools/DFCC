#!/usr/bin/env bash
# Build the stand-alone DFCC executable on Linux/macOS:  packaging/build_exe.sh  ->  dist/DFCC/DFCC
set -e
cd "$(dirname "$0")/.."
python3 -m venv build_venv && . build_venv/bin/activate
pip install -q --upgrade pip && pip install -q ".[gui]" pyinstaller
cd packaging && pyinstaller --noconfirm --distpath ../dist --workpath ../build dfcc.spec
../dist/DFCC/DFCC --version
