# Full TempGNN Result Inventory

## Included, Regenerable Paper Figure Records

- `results/paper_reproduction/*.csv`
- `results/paper_reproduction/*.svg`
- `results/paper_reproduction/figure_data_manifest.csv`
- `results/paper_reproduction/paper_figure_values.csv`
- `results/paper_reproduction/all_figure_data.csv`
- `tempgenn/paper_reference_data.py`
- `reference_inputs/README.md`

The Python source records regenerate these source-labeled paper plotting
outputs. The CSV/SVG files are included in the AE archive for direct reviewer
inspection; they are deterministic paper-reference reconstructions, not fresh
hardware executions.

## Fresh U280 Mechanism Evidence

- Four artifacts: `artifacts/u280/TempGNN`, `MATG`, `ViTeGNN`, and `RTGA`
- Baseline source: `hardware/baselines/`
- Configuration: `configs/u280_core_reproduction.json`
- Latest timestamped run: `results/reviewer_u280_runs/20260717T024537Z`
- Raw rows: `results/reviewer_u280_runs/<run-id>/raw/*/measurements.csv`
- Provenance: `results/reviewer_u280_runs/<run-id>/provenance.json`
- Derived figures: `results/reviewer_u280_runs/<run-id>/derived_comparison_figures/`
- Verification: `results/reviewer_u280_runs/<run-id>/verification.md`

## Additional Evidence

- TempGNN sanity board logs and layout: `results/board_u280/`
- Optional, not pre-packaged TGL edge-stream counters: `results/q14_real_tgl_edges/`
- Reviewer reports: `results/ae_report/`
