#!/usr/bin/env bash
# The skill ships inside the repo; use the canonical installer so the two
# copies cannot drift.
set -euo pipefail
SCRIPT_DIR="$(python3 -c 'import os,sys; print(os.path.dirname(os.path.realpath(sys.argv[1])))' "${BASH_SOURCE[0]}")"
exec "$SCRIPT_DIR/../../setup.sh"
