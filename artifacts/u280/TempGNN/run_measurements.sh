#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/../run_measurements_common.sh" \
  --solution TempGNN --kernel-name tempgnn_forward_kernel "$@"
