#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KERNEL="${1:-stats}"
BUILD_DIR="${ROOT_DIR}/build/hardware_csim"
mkdir -p "${BUILD_DIR}"

if [[ "${KERNEL}" == "forward" ]]; then
  SOURCE="${ROOT_DIR}/hardware/src/tempgnn_forward_kernel.cpp"
  TESTBENCH="${ROOT_DIR}/hardware/tb/tempgnn_forward_tb.cpp"
  OUTPUT="${BUILD_DIR}/tempgnn_forward_tb"
else
  SOURCE="${ROOT_DIR}/hardware/src/tempgnn_kernel.cpp"
  TESTBENCH="${ROOT_DIR}/hardware/tb/tempgnn_tb.cpp"
  OUTPUT="${BUILD_DIR}/tempgnn_tb"
fi

CXX="${CXX:-g++}"
"${CXX}" -std=c++17 -O2 \
  -I"${ROOT_DIR}/hardware/include" \
  "${SOURCE}" \
  "${TESTBENCH}" \
  -o "${OUTPUT}"

"${OUTPUT}"
