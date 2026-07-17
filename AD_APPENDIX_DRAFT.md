# Artifact Description Appendix

Paper ID: `pap142`

Requested SC26 badge review: all three artifact badges.

## Part 1: Contributions and Artifacts

### Main Contributions

- `C1`: Target Dependency Packets (TDPs) expose target-centric temporal
  dependencies and branch-level parallelism.
- `C2`: DDTC constructs TDPs on demand to reduce target-irrelevant work and
  data movement.
- `C3`: OATS and PHLE reuse overlapping dependency packets while preserving
  ordered target updates.
- `C4`: TempGNN is evaluated on an Alveo U280 across six temporal datasets and
  four TGNN models, including accelerator-baseline comparisons.

### Computational Artifacts

| Artifact | Contents | Contributions and paper results |
| --- | --- | --- |
| `A1` | TempGNN, MATG, ViTeGNN, and RTGA U280 sources, xclbins, XRT hosts, inputs, tests, and measurement workflow | Supports `C1-C4`; reproduces the U280 latency behavior used in the accelerator comparison |
| `A2` | `results/result.csv`, `tempgenn/result.py`, and the CSV/SVG figure generator | Supports inspection of `C1-C4`; regenerates Fig.2, Fig.4(a), Fig.9(b), and Fig.10-Fig.14 |

Artifact DOI:
`https://doi.org/10.5281/zenodo.21417187`.

Development repository:
`https://github.com/TempGNN-Program/TempGNN`.

Frozen release: `sc26-ae-pap142-v1.0`.

## Part 2: Artifact Identification

## 1. Download

```bash
git clone https://github.com/TempGNN-Program/TempGNN.git
cd TempGNN
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Environment and Inputs

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

XRT is available from `https://github.com/Xilinx/XRT`; Python is available
from `https://www.python.org/`. A reviewer account on the matching U280 host is
provided through the private SC26 submission channel.

`A1` uses bundled prefixes of WK, MC, RT, LM, WT, and GT with JODIE, TGN,
TGAT, and APAN. Source URLs, selection metadata, and hashes accompany the
inputs under `external/u280_dataset_samples/`. `A2` uses the packaged
`results/result.csv`.

## 3. Run TempGNN and Baseline Accelerators on U280

Relation to contributions: `A1` exercises the TempGNN mechanisms and the
U280 evaluation supporting `C1-C4`.

```bash
source /opt/xilinx/xrt/setup.sh
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

Workflow:

```text
check four U280 artifacts
  -> prepare the six-dataset/four-model inputs
  -> run TempGNN, MATG, ViTeGNN, and RTGA three times
  -> write raw measurement CSVs
  -> aggregate mean latency
```

Expected arithmetic mean latency:

| U280 implementation | Mean latency (ms) |
| --- | ---: |
| TempGNN | 1.296553 |
| MATG | 9.966618 |
| ViTeGNN | 2.869752 |
| RTGA | 4.192824 |

A successful run exits with status zero, records all four implementations, and
writes fresh measurements under `results/reviewer_u280_runs/<run-id>/`.
TempGNN should retain the lowest mean latency and remain close to 1.3 ms.

Expected time:

| Setup | Execution | Analysis |
| ---: | ---: | ---: |
| 10-20 min | 30-90 min | less than 5 min |

Rebuilding xclbins is optional and is not part of the direct review workflow.

## 4. Generate the Remaining Figures from result.csv

Relation to contributions: `A2` regenerates the paper-result plots associated
with `C1-C4`.

```bash
python3 -m scripts.reproduce_paper_figures
```

Workflow:

```text
results/result.csv
  -> validate and group the result rows
  -> generate per-figure CSV files
  -> generate matching SVG figures and a manifest
```

Expected output: nine CSV/SVG figure pairs for Fig.2, Fig.4(a), Fig.9(b), and
Fig.10-Fig.14 under `results/paper_reproduction/`. The manifest must identify
`results/result.csv` as the input.

| Setup | Execution | Analysis |
| ---: | ---: | ---: |
| less than 5 min | less than 1 min | 2-5 min |

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
