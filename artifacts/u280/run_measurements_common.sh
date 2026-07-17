#!/usr/bin/env bash
set -euo pipefail

SOLUTION=""
KERNEL_NAME=""
HOST=""
XCLBIN=""
DEVICE="0"
DATASETS=""
MODELS=""
REPETITIONS="3"
OUTPUT=""
BASELINE_REFERENCE=""
REQUESTED_FREQUENCY_MHZ="225"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --solution) SOLUTION="$2"; shift 2 ;;
    --kernel-name) KERNEL_NAME="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --xclbin) XCLBIN="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    --datasets) DATASETS="$2"; shift 2 ;;
    --models) MODELS="$2"; shift 2 ;;
    --repetitions) REPETITIONS="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --baseline-reference) BASELINE_REFERENCE="$2"; shift 2 ;;
    --requested-frequency-mhz) REQUESTED_FREQUENCY_MHZ="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

for required in SOLUTION KERNEL_NAME HOST XCLBIN DATASETS MODELS OUTPUT; do
  if [[ -z "${!required}" ]]; then
    echo "Missing required option: ${required}" >&2
    exit 2
  fi
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXTRA_ARGS=()
if [[ "${SOLUTION}" != "TempGNN" ]]; then
  if [[ -z "${BASELINE_REFERENCE}" ]]; then
    BASELINE_REFERENCE="${ROOT_DIR}/artifacts/u280/${SOLUTION}/bin/baseline_csim"
  fi
  EXTRA_ARGS+=(--baseline-reference "${BASELINE_REFERENCE}")
fi
exec python3 "${ROOT_DIR}/scripts/measure_u280_forward.py" \
  --solution "${SOLUTION}" \
  --kernel-name "${KERNEL_NAME}" \
  --host "${HOST}" \
  --xclbin "${XCLBIN}" \
  --device "${DEVICE}" \
  --datasets "${DATASETS}" \
  --models "${MODELS}" \
  --repetitions "${REPETITIONS}" \
  --requested-frequency-mhz "${REQUESTED_FREQUENCY_MHZ}" \
  --output "${OUTPUT}" \
  "${EXTRA_ARGS[@]}"
