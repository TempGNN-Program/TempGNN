# U280 AE Runbook

## Environment

```bash
source /opt/xilinx/xrt/setup.sh
```

## Run TempGNN and Baseline Accelerators

```bash
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

## Generate Figures from result.csv

```bash
python3 -m scripts.reproduce_paper_figures
```

All figure values are read from `results/result.csv`.
