# TempGNN AE Bridge Claim Map

This file maps the package contents to the AE bridge criteria. See `AE_APPENDIX_DRAFT.md` for the measurement boundary.

## Bridge Summary

| Bridge | Evidence in package | How to verify |
| --- | --- | --- |
| Artifacts Available | Source, scripts, tests, fixtures, generated CSV/SVG figures, U280 logs, xclbin, and packaged reports | Unpack the archive and inspect `README.md`, `ENVIRONMENT.md`, `results/ae_report/`, `hardware/`, `scripts/`, and `tests/` |
| Artifacts Evaluated Functional | Python tests, figure regeneration, Q14 profiling, one U280 forward-path xclbin, XRT host, board PASS logs, timing summary, layout image, and baseline measurement verification | Run `make smoke`, `make report`, and on U280 run `make u280-run U280_DEVICE=0` |
| Results Reproduced | Motivation, speedup, energy, ablation, sensitivity figures, and baseline measurement tables regenerated from reproduced measured inputs | Run `python3 -m scripts.reproduce_paper_figures`, `python3 -m scripts.derive_comparison_figures`, and inspect `results/baselines_u280/verify_summary.md` |

## Hardware Evidence

| Evidence | File |
| --- | --- |
| U280 forward-path board summary | `results/board_u280/summary.json` |
| U280 board logs | `results/board_u280/smoke.log`, `results/board_u280/tbscale.log`, `results/board_u280/maxbatch.log` |
| U280 routed layout figure | `results/board_u280/tempgnn_u280_fpga_layout.png` |
| FPGA baseline U280 measurements | `results/baselines_u280/manifest.md` |
| Raw-derived comparison figures | `results/derived_comparison_figures/fig10_speedup_tglite_cpu.csv`, `fig11_speedup_matg.csv`, `fig12_energy_tempgnn.csv` |
| Figure data manifest | `results/paper_reproduction/figure_data_manifest.csv` |
| Combined plotted values | `results/paper_reproduction/all_figure_data.csv` |
| AE consolidated report | `results/ae_report/ae_summary.md` |
