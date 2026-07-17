# TempGNN AE Quickstart

## Run TempGNN and Baseline Accelerators on U280

```bash
source /opt/xilinx/xrt/setup.sh
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

Fresh measurements are written under
`results/reviewer_u280_runs/<run-id>/`.

## Generate Figures from result.csv

```bash
python3 -m scripts.reproduce_paper_figures
```

All figure values are read from `results/result.csv`. Generated CSV/SVG files
are written to `results/paper_reproduction/`.
