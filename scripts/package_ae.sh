#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

pkg="${1:-ae_export/pap142_tempgnn_sc26_ae_u280.tgz}"
archive_root="pap142_tempgnn_sc26_ae"
mkdir -p "$(dirname "$pkg")"

entries=(
  README.md ENVIRONMENT.md AD_APPENDIX_DRAFT.md AE_APPENDIX_DRAFT.md SC26_AE_REVIEWER_GUIDE.md ZENODO_RELEASE_CHECKLIST.md requirements.txt .gitattributes .gitignore Makefile
  scripts tempgenn tests hardware configs artifacts release reference_inputs
  results/ae_report
  results/q14_real_tgl_edges
  results/paper_reproduction
  results/board_u280
  results/fixtures
)

optional_entries=(
  LICENSE
  CITATION.cff
  .zenodo.json
  external/u280_dataset_samples
  results/generated_u280_comparison_fixtures
  results/reviewer_u280_runs
)

for path in "${optional_entries[@]}"; do
  if [[ -e "$path" ]]; then
    entries+=("$path")
  fi
done

python3 -m scripts.run_u280_core_reproduction --preflight-only

tar -czf "$pkg" \
  --transform="s|^|${archive_root}/|" \
  --exclude='**/__pycache__' \
  --exclude='*.pyc' \
  --exclude='results/ae_report/old_*' \
  --exclude='results/ae_report/ae_summary.json' \
  --exclude='results/paper_reproduction/summary.json' \
  --exclude='results/q14_real_tgl_edges/q14_dataset_model_summary.json' \
  --exclude='external/tgl/DATA' \
  --exclude='*/_x' \
  --exclude='*/_x/*' \
  --exclude='*/.Xil' \
  --exclude='*/.Xil/*' \
  --exclude='*/.ipcache' \
  --exclude='*/.ipcache/*' \
  --exclude='hardware/vitis/_x' \
  --exclude='hardware/vitis/.Xil' \
  --exclude='hardware/vitis/.ipcache' \
  --exclude='hardware/vitis/v++_*.backup.log' \
  --exclude='hardware/vitis/xcd.log' \
  --exclude='results/board_u280/layout_hook/*.dcp' \
  "${entries[@]}"

ls -lh "$pkg"
sha256sum "$pkg" > "${pkg}.sha256"
cat "${pkg}.sha256"
