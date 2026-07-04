#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

pkg="${1:-tempgnn_ae_u280_measured_20260705_single_fpga.tgz}"

entries=(
  README.md ENVIRONMENT.md AD_APPENDIX_DRAFT.md AE_APPENDIX_DRAFT.md SC26_AE_REVIEWER_GUIDE.md requirements.txt .gitignore Makefile
  scripts tempgenn tests hardware
  results/ae_report
  results/q14_real_tgl_edges
  results/baselines_u280
  results/derived_comparison_figures
  results/paper_reproduction
  results/board_u280
  results/fixtures
)

optional_entries=(
  build/vitis_u280_forward_hw/tempgnn_forward_kernel.hw.xclbin
  build/vitis_u280_forward_hw/tempgnn_forward_kernel.hw.xclbin.info
  build/vitis_u280_forward_hw/tempgnn_forward_kernel.hw.xclbin.link_summary
  build/vitis_u280_forward_hw/tempgnn_forward_xrt_host
)

for path in "${optional_entries[@]}"; do
  if [[ -e "$path" ]]; then
    entries+=("$path")
  fi
done

tar -czf "$pkg" \
  --exclude='**/__pycache__' \
  --exclude='*.pyc' \
  --exclude='results/ae_report/old_*' \
  --exclude='results/ae_report/ae_summary.json' \
  --exclude='results/paper_reproduction/summary.json' \
  --exclude='results/q14_real_tgl_edges/q14_dataset_model_summary.json' \
  --exclude='external/tgl/DATA' \
  --exclude='hardware/vitis/_x' \
  --exclude='hardware/vitis/.Xil' \
  --exclude='hardware/vitis/.ipcache' \
  --exclude='hardware/vitis/v++_*.backup.log' \
  --exclude='hardware/vitis/xcd.log' \
  --exclude='results/board_u280/layout_hook/*.dcp' \
  --exclude='build/vitis_u280_forward_hw/*.xo' \
  "${entries[@]}"

ls -lh "$pkg"
