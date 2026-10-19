#!/usr/bin/env bash
# The skill ships inside the repo; use the canonical installer so the two
# copies cannot drift.
set -euo pipefail
SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/../../setup.sh"
