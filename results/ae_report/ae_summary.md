# TempGNN AE Reproduction Report

## U280 Latency

Latest run: `results/reviewer_u280_runs/20260717T024537Z`

| System | Rows | Failed functional rows | Mean latency (ms) |
| --- | ---: | ---: | ---: |
| TempGNN | 72 | 0 | 1.296553 |
| MATG | 72 | 0 | 9.966618 |
| ViTeGNN | 72 | 0 | 7.022530 |
| RTGA | 72 | 0 | 4.914013 |

Run on U280:

```bash
source /opt/xilinx/xrt/setup.sh
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

## Figures

All remaining figure values are read from `results/result.csv`.

```bash
python3 -m scripts.reproduce_paper_figures
```
