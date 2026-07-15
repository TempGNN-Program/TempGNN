# Full TempGNN Result Inventory

## Packaged Reference Reconstruction

- `results/paper_reproduction/*.csv`
- `results/paper_reproduction/*.svg`
- `results/paper_reproduction/figure_data_manifest.csv`
- `results/paper_reproduction/all_figure_data.csv`
- `reference_inputs/paper_figure_values.csv`
- `reference_inputs/README.md`

These files regenerate source-labeled paper plotting inputs; they are not fresh hardware executions.

## Fresh U280 Mechanism Evidence

- Four artifacts: `artifacts/u280/TempGNN`, `MATG`, `ViTeGNN`, and `RTGA`
- Baseline source: `hardware/baselines/`
- Configuration: `configs/u280_core_reproduction.json`
- Latest timestamped run: `results/reviewer_u280_runs/pap142_u280_measured_20260715T052052Z`
- Raw rows: `results/reviewer_u280_runs/<run-id>/raw/*/measurements.csv`
- Provenance: `results/reviewer_u280_runs/<run-id>/provenance.json`
- Derived figures: `results/reviewer_u280_runs/<run-id>/derived_comparison_figures/`
- Verification: `results/reviewer_u280_runs/<run-id>/verification.md`

## Additional Evidence

- TempGNN sanity board logs and layout: `results/board_u280/`
- Real TGL edge-stream counters: `results/q14_real_tgl_edges/`
- Reviewer reports: `results/ae_report/`
