# TempGNN SC26 AE Reviewer Guide

The AD defines two artifacts:

- `A1`: TempGNN, MATG, ViTeGNN, and RTGA on U280.
- `A2`: `results/result.csv` and the CSV/SVG figure generator.

## Download

```bash
git clone https://github.com/TempGNN-Program/TempGNN.git
cd TempGNN
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Artifact DOI:
`https://doi.org/10.5281/zenodo.21417187`.

Frozen release: `sc26-ae-pap142-v1.0`.

## Environment

```text
Board: AMD/Xilinx Alveo U280, xcu280-fsvh2892-2L-e
Platform: xilinx_u280_gen3x16_xdma_1_202211_1
OS: Ubuntu 22.04 x86_64
XRT: 2.16.204
Vitis/Vivado: 2023.2 (only required for rebuilding xclbins)
GCC: 11.4.0
GNU Make: 4.3
Python: 3.10 or newer
```

The U280 account is provided through the private SC26 submission channel.

## Review Tasks

| Task | Execution | Expected result |
| --- | ---: | --- |
| U280 latency | 30-90 min | Four fresh latency results; TempGNN is lowest at about 1.3 ms |
| Figure generation | less than 1 min | Nine CSV/SVG pairs generated from `results/result.csv` |

## Run TempGNN and Baseline Accelerators on U280

```bash
source /opt/xilinx/xrt/setup.sh
xrt-smi examine
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

The workflow checks four artifacts, runs six datasets and four models with
three repetitions, writes raw CSVs, and aggregates latency under
`results/reviewer_u280_runs/<run-id>/`.

| U280 implementation | Mean latency (ms) |
| --- | ---: |
| TempGNN | 1.296553 |
| MATG | 9.966618 |
| ViTeGNN | 7.022530 |
| RTGA | 4.914013 |

The run is successful when the command exits with status zero, all four
implementations are present, and TempGNN retains the lowest mean latency close
to 1.3 ms.

## Generate Figures from result.csv

```bash
python3 -m scripts.reproduce_paper_figures
```

The workflow reads `results/result.csv` and generates the CSV/SVG pairs for
Fig.2, Fig.4(a), Fig.9(b), and Fig.10-Fig.14 under
`results/paper_reproduction/`. The run is successful when all nine pairs exist
and `figure_data_manifest.csv` identifies `results/result.csv` as the input.

## Baseline Status

- MATG: independently reproduced from the IPDPS 2022 paper and its partial
  public HLS headers; includes a distinct source, runner, and U280 xclbin.
- ViTeGNN: independently reproduced from the TPDS 2025 paper; includes a
  distinct source, runner, and U280 xclbin.
- RTGA: independently reproduced from the DAC 2024 paper; includes a distinct
  source, runner, and U280 xclbin.
- Cascade and TGLite-CPU: retained only as packaged paper comparison records in
  this repository; no fresh execution of those external stacks is claimed.
- TempGNN: includes HLS kernels, testbenches, Vitis build scripts, XRT host
  code, U280 forward-path board logs, and its own U280 xclbin.

The three baselines are independent, paper-based forward-path reproductions,
not the authors' complete original stacks.

## Metric Meaning

`DDTC` is dependency-driven TDP construction. `OATS` is overlap-aware TDP
synchronization.

`packet_reuse_factor` measures how many per-target packet materializations
collapse into unique PHLE packets. `memory_bytes` is packet state/metadata
traffic. `cycles` is the kernel's cycle proxy used by C-sim and exported
fixture stats. HLS reports provide C/RTL latency after synthesis/cosim.

## License

This artifact is licensed under the Apache License 2.0. See `LICENSE`.
