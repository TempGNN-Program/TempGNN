# Artifact Evaluation Appendix

Paper ID: `pap142`

## 1. Download

```bash
git clone https://github.com/TempGNN-Program/TempGNN.git
cd TempGNN
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Environment

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

## 3. Run TempGNN and Baseline Accelerators on U280

```bash
source /opt/xilinx/xrt/setup.sh
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

The command runs TempGNN, MATG, ViTeGNN, and RTGA. The expected arithmetic
mean latency over 6 datasets and 4 models is:

| U280 implementation | Mean latency (ms) |
| --- | ---: |
| TempGNN | 1.296553 |
| MATG | 9.966618 |
| ViTeGNN | 2.869752 |
| RTGA | 4.192824 |

Fresh measurements are written under
`results/reviewer_u280_runs/<run-id>/`.

## 4. Generate the Remaining Figures from result.csv

All remaining figure values are read from `results/result.csv`.

```bash
python3 -m scripts.reproduce_paper_figures
```

The generated CSV/SVG files are written to
`results/paper_reproduction/`.

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
not the authors' complete original stacks. This distinction is intentional and
is recorded in every fresh run's provenance.

## Metric Meaning

`DDTC` is dependency-driven TDP construction. `OATS` is overlap-aware TDP
synchronization.

`packet_reuse_factor` measures how many per-target packet materializations
collapse into unique PHLE packets. `memory_bytes` is packet state/metadata
traffic. `cycles` is the kernel's cycle proxy used by C-sim and exported
fixture stats. HLS reports provide C/RTL latency after synthesis/cosim.

## License

This artifact is licensed under the Apache License 2.0. See `LICENSE`.
