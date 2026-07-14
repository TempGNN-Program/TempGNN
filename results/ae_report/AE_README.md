# TempGNN AE Quickstart

The package has two deliberately separate paths:

1. `make smoke` regenerates source-labeled paper-reference figures and runs software tests.
2. `make ae-core-u280` executes TempGNN, MATG, ViTeGNN, and RTGA as four distinct U280 xclbins and derives fresh mechanism-level comparison rows. A diagnostic tolerance FAIL is recorded without failing an otherwise complete hardware run.

MATG, ViTeGNN, and RTGA are paper-based forward-path reproductions. Their implemented mechanisms and limitations are documented in `hardware/baselines/README.md`. This bounded Q10 path is not a paper-equivalent rerun of Fig.11/Fig.12.

Paper-reference inputs live in `reference_inputs/paper_figure_values.csv`.
Every row identifies an exact workbook value or a vector-geometry digitization;
these rows are never substituted for fresh U280 measurements.

## CPU-Only

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make smoke
make report
```

## U280

```bash
source /opt/xilinx/xrt/setup.sh
make u280-core-preflight
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

Fresh status: **NOT RUN**.

Raw rows, logs, per-sample power evidence, hashes, figures, and verification are written under `results/reviewer_u280_runs/<run-id>/`.
