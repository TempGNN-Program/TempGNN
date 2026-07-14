# Paper-Based U280 Baseline Reproductions

This directory contains independent, clean-room forward-path reproductions of
MATG, ViTeGNN, and RTGA. They were implemented from the published algorithm and
architecture descriptions because complete author RTL/HLS projects that build
in this U280 environment were not available. They are not the authors' original
source trees and are not claimed to be bit-for-bit substitutes for those trees.

The reproductions hold the graph fixture, fixed-point format, host, XRT timing
method, U280 shell, requested 225 MHz clock, and board-power sampling method
constant. Each baseline has a separate top-level kernel, synthesis result, and
xclbin. `scripts/run_u280_core_reproduction.py` rejects byte-identical xclbins.
It cross-checks each xclbin link request against the Vivado `ap_clk` connection
and nonnegative post-route WNS/TNS, then rejects normalized comparison
generation if the four implemented kernel clocks differ.
Each sampler scans at most 64 recent history slots to collect up to the requested
20 temporally valid candidates, so events after the target timestamp do not
silently consume the comparison fanout.

## Implemented Paper Mechanisms

| Reproduction | Mechanisms present in the kernel | Bounded configuration implemented here |
| --- | --- | --- |
| MATG | timestamp-only simplified attention, BRAM-bound 128-entry time-score ROM, top-k temporal-neighbor pruning, fixed-point GRU/GNN update | One kernel CU; local pruning budgets 2/4/6 and at most six retained neighbors |
| ViTeGNN | `bal`-inspired shift/scan/compact neighbor-update behavior, BRAM-buffered recent-history reads, duplicate removal, lightweight temporal attention, and model-selectable update | One kernel CU and at most four retained neighbors; the optional cached-output selector is not the paper's separate `thpt` maintenance path |
| RTGA | temporal-tree triplets, BRAM-buffered recent-history reads, cross-root visited-edge suppression, eight parallel TAU lanes, temporal-aware `degree/timestamp` cache priority, temporal aggregation | 8 TAUs and a bounded on-chip TADC cache |

The shared model selector exercises adapters for JODIE, TGN, TGAT, and APAN.
The adapters cover the measured forward path only. Training, knowledge
distillation, task accuracy, full-dataset preprocessing, and the complete
original runtime stacks are outside this reproduction and must not be inferred
from these measurements.

The paper-level comparison is not reproduced by these reduced adapters. The
packaged path is 8-dimensional Q10 with deterministic stand-in weights and
bounded real-dataset prefixes; the TempGNN paper specifies full model
configurations, default 32-bit floating point, full evaluation streams, and a
different FPGA power method. The resulting measurements are useful functional
and mechanism evidence, not a substitute for the paper's Fig.11/Fig.12 data.

## Sources Used

- H. Zhou et al., "Model-Architecture Co-Design for High Performance Temporal
  GNN Inference on FPGA," IPDPS 2022, DOI
  `10.1109/IPDPS53621.2022.00111` (MATG). The public repository at
  `https://github.com/zjjzby/TGNN-FPGA-IPDPS2022` at commit
  `27b5a603e30a308b02e8d9f44395da391685cfc1` was consulted for partial HLS
  context; it did not contain a complete U280 host/build/top-level flow. The
  kernel in this artifact is independently written and does not copy that
  repository's source tree.
- H. Zhou et al., "ViTeGNN: Towards Versatile Inference of Temporal Graph
  Neural Networks on FPGA," IEEE TPDS 36(3), 2025, DOI
  `10.1109/TPDS.2024.3521897`.
- H. Yu et al., "RTGA: A Redundancy-free Accelerator for High-Performance TGNN
  Inference," DAC 2024, DOI `10.1145/3649329.3656241`.

## Build

On the measured server:

```bash
source /tools/Xilinx/Vitis/2023.2/settings64.sh
source /opt/xilinx/xrt/setup.sh
make u280-build
make u280-baseline-build
```

Run these commands serially. Each implementation uses a build-local Vivado IP
cache; launching three U280 links concurrently can exceed 64 GB of host memory.
The root targets preserve the four complete build logs consumed by
`make u280-stage-artifacts`.

The build products are written below `build/baselines/`. After all four links
complete, `make u280-stage-artifacts` copies the runnable files to
`artifacts/u280/<system>/bin/`, selects the post-route reports, and writes
SHA256 provenance. The staging step normalizes login, host, and absolute build
paths in the xclbin `BUILD_METADATA` and `SYSTEM_METADATA` sections for
double-blind review. It dumps and hashes the FPGA `BITSTREAM` section before
and after normalization and fails unless those hashes are identical.

## Measurement Contract

`scripts/fetch_u280_dataset_samples.py` streams a deterministic 8,192-event
prefix from each public real dataset, sorts that selected prefix by timestamp,
and records its URL, selection rule, source-order status, and SHA256.
`scripts/generate_u280_comparison_fixture.py` converts those samples into
bounded fixtures for every dataset/model pair. Synthetic generation requires
an explicit `--synthetic` flag and is reserved for C-sim.
`scripts/measure_u280_forward.py` calibrates the number
of kernel iterations, measures XRT launch-to-completion latency, repeatedly
samples total U280 board power using `xbutil examine --report electrical`, and
writes one raw CSV row per repetition. Energy is calculated as
`latency_ms * board_power_w`, which is numerically millijoules.

The output is a fresh U280 measurement of these packaged mechanism
reproductions. Numerical agreement or disagreement with a paper figure is
diagnostic only; values are never substituted from the reference CSVs.

For a function-by-function link between the paper terminology and this source,
see `MECHANISM_MAP.md`.
