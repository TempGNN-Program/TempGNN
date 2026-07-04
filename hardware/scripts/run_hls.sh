#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODE="${1:-csynth}"
KERNEL="${2:-stats}"

if [[ "${KERNEL}" == "forward" ]]; then
  TCL="${ROOT_DIR}/hardware/hls/tempgnn_forward_hls.tcl"
else
  TCL="${ROOT_DIR}/hardware/hls/tempgnn_hls.tcl"
fi

if command -v vitis-run >/dev/null 2>&1; then
  if [[ "${MODE}" == "cosim" ]]; then
    export TEMPGNN_HLS_COSIM=1
  fi
  vitis-run --mode hls --tcl "${TCL}"
elif command -v vitis_hls >/dev/null 2>&1; then
  HLS_BIN="vitis_hls"
elif command -v vivado_hls >/dev/null 2>&1; then
  HLS_BIN="vivado_hls"
else
  echo "vitis-run/vitis_hls/vivado_hls not found in PATH. Source Xilinx/Vitis settings first." >&2
  exit 127
fi

if [[ -n "${HLS_BIN:-}" ]]; then
  if [[ "${MODE}" == "cosim" ]]; then
    "${HLS_BIN}" -f "${TCL}" cosim
  else
    "${HLS_BIN}" -f "${TCL}"
  fi
fi
