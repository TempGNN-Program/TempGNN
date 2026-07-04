#!/usr/bin/env bash
set -euo pipefail
source /opt/xilinx/xrt/setup.sh
build/vitis_u280_forward_hw/tempgnn_forward_xrt_host \
  build/vitis_u280_forward_hw/tempgnn_forward_kernel.hw.xclbin \
  results/fixtures/forward_maxbatch \
  20 2 16 1 1 0
