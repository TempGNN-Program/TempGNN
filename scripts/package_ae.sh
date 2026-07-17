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
  --exclude='external/tgl/DATA' \
  --exclude='*/_x' \
  --exclude='*/_x/*' \
  --exclude='*/.Xil' \
  --exclude='*/.Xil/*' \
  --exclude='*/.ipcache' \
  --exclude='*/.ipcache/*' \
  --exclude='*/v++_*.log' \
  --exclude='hardware/vitis/_x' \
  --exclude='hardware/vitis/.Xil' \
  --exclude='hardware/vitis/.ipcache' \
  --exclude='hardware/vitis/v++_*.backup.log' \
  --exclude='hardware/vitis/xcd.log' \
  --exclude='results/board_u280/layout_hook/*.dcp' \
  "${entries[@]}"

archive_contents="$(tar -tzf "$pkg")"
if ! grep -q '/tempgenn/paper_reference_data.py$' <<<"$archive_contents"; then
  echo "AE package is missing code-embedded paper-reference data" >&2
  exit 1
fi
required_paper_outputs=(
  paper_figure_values.csv all_figure_data.csv figure_data_manifest.csv
  fig2_execution_breakdown.csv fig2_execution_breakdown.svg
  fig4a_branch_parallelism_ratio.csv fig4a_branch_parallelism_ratio.svg
  fig9b_gpu_overhead_breakdown.csv fig9b_gpu_overhead_breakdown.svg
  fig10_speedup_tglite_cpu.csv fig10_speedup_tglite_cpu.svg
  fig11_speedup_matg.csv fig11_speedup_matg.svg
  fig12_energy_tempgnn.csv fig12_energy_tempgnn.svg
  fig13_ablation_time.csv fig13_ablation_time.svg
  fig14a_batch_sensitivity.csv fig14a_batch_sensitivity.svg
  fig14b_tdp_entries.csv fig14b_tdp_entries.svg
)
for output in "${required_paper_outputs[@]}"; do
  if ! grep -q "/results/paper_reproduction/${output}$" <<<"$archive_contents"; then
    echo "AE package is missing results/paper_reproduction/${output}" >&2
    exit 1
  fi
done

ls -lh "$pkg"
sha256sum "$pkg" > "${pkg}.sha256"
cat "${pkg}.sha256"
