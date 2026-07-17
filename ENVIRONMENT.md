# TempGNN AE Environment

This file records the software and hardware environment used to generate the packaged TempGNN AE evidence.

## Optional Software-Check Environment

This optional path regenerates CSV/SVG figures from `results/result.csv`, runs unit
tests, and regenerates the AE report. It does not execute a CPU performance
baseline and does not require FPGA hardware. The recommended core review path
is `make ae-core-u280` on the provided U280 host.

Minimum requirements:

```text
OS: Linux x86_64
Python: 3.10 or newer
Build tools: GNU Make, Bash, tar, gzip
Python packages: none beyond the standard library for core CSV/SVG generation
```

Optional setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make smoke
make report
```

`requirements.txt` is intentionally minimal. Optional layout rendering can use matplotlib if a reviewer regenerates PNG/SVG layout figures from routed LOC exports.

## Recorded U280 Hardware Environment

The U280 forward-path board evidence was generated on:

```text
Host: u280-ae-host
OS: Ubuntu 22.04.5 LTS
Kernel: Linux 5.15.0-122-generic x86_64
Python: 3.10.12
GNU Make: 4.3
GCC: 11.4.0
```

FPGA board and platform:

```text
Board: AMD/Xilinx Alveo U280
Device: xcu280-fsvh2892-2L-e
Shell: xilinx_u280_gen3x16_xdma_base_1
Platform: xilinx_u280_gen3x16_xdma_1_202211_1
```

FPGA software stack:

```text
Vitis/Vivado: 2023.2
v++ build: 4026344
XRT: 2.16.204
XOCL: 2.16.204
XCLMGMT: 2.16.204
```

Environment setup used on the U280 server:

```bash
source /opt/xilinx/xrt/setup.sh
source /tools/Xilinx/Vitis/2023.2/settings64.sh
```

## Platform Package Path Used In The Recorded Run

```text
/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
```

If a reviewer has a different installation path, pass it explicitly:

```bash
make u280-build U280_PLATFORM=/path/to/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
```

## What Is Required For Each AE Path

| Path | Requires U280 | Requires Vitis/Vivado | Expected runtime |
| --- | ---: | ---: | --- |
| `make smoke` | No | No | seconds |
| `make report` | No | No | seconds |
| `python3 -m scripts.reproduce_paper_figures` | No | No | seconds |
| `make q14` after `make data` | No | No | minutes |
| `make u280-run` with packaged xclbin | Yes | No, XRT required | minutes |
| `make u280-core-preflight` | No | No | seconds |
| `make ae-core-u280` with four packaged xclbins | Yes | No, XRT required | minutes |
| `make u280-build` | Yes for board run | Yes | multi-hour |

See `AE_APPENDIX_DRAFT.md` for the measurement boundary.
