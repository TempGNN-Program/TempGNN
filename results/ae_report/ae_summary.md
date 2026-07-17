# TempGNN AE Reproduction Report

## Scope

The figure command regenerates paper-reference CSV/SVG records from source-labeled Python constants; it does not rerun CPU, GPU, or FPGA baselines. The one-command U280 path executes four distinct xclbins and writes new latency, total-board-power, checksum, and provenance evidence before regenerating this report. MATG, ViTeGNN, and RTGA are independent paper-based forward-path reproductions, not the baseline authors' complete original stacks.
The fresh command is a bounded mechanism-level comparison on real-dataset prefixes. Each xclbin link request is cross-checked against the Vivado-connected kernel clock and nonnegative post-route WNS/TNS. Every implementation must keep one stable timing-closed clock across its rows; raw latency is compared without frequency rescaling. It is not paper-equivalent: the packaged kernels use an 8-dimensional Q10 forward path and `xbutil` board power, while the paper specifies full models, default 32-bit floating point, full evaluation streams, and post-route Vivado power estimates.

See `AE_APPENDIX_DRAFT.md` for the authoritative measurement boundary.

## Code-Embedded Paper Reference Averages

These are explicit AVG cells/bars from the source-labeled paper-reference input:

| Record | Value |
| --- | ---: |
| TempGNN / TGLite-CPU speedup | 132.80x |
| TempGNN-G / TGLite-CPU speedup | 10.85x |
| Cascade / TGLite-CPU speedup | 5.22x |
| TempGNN / MATG plotted AVG bar | 7.79x |
| Cascade / TempGNN energy | 33.55x |
| Without DDTC normalized time | 3.08x |
| Without OATS normalized time | 1.77x |

The Fig.11 vector export contains a 7.7889x TempGNN/MATG AVG bar, while the paper prose reports 7.6x. The source discrepancy is preserved rather than overwritten.

## Fresh U280 Status

Latest run: `results/reviewer_u280_runs/20260717T024537Z`

| System | Rows | Failed functional rows | Mean latency (ms) |
| --- | ---: | ---: | ---: |
| TempGNN | 72 | 0 | 1.296553 |
| MATG | 72 | 0 | 9.966618 |
| ViTeGNN | 72 | 0 | 2.869752 |
| RTGA | 72 | 0 | 4.192824 |

Fresh measured TempGNN/MATG all-workload average speedup: **7.8889x**.

| Check | Max relative error | Threshold | Status |
| --- | ---: | ---: | --- |
| fig11_speedup_matg | 3.389464 | 0.050000 | FAIL |
| fig12_energy_tempgnn | 0.933125 | 0.100000 | FAIL |

A numerical tolerance PASS does not establish the Results Reproduced bridge while provenance marks the method as not paper-equivalent. Reference CSV values are never substituted for measured rows.

## Hardware

Each comparison build uses the per-design timing-closed clock recorded in its raw rows and post-route evidence on `xilinx_u280_gen3x16_xdma_1_202211_1`; no frequency rescaling is applied.
The packaged TempGNN build reports WNS=0.002 ns and TNS=0.0 ns.

## Reviewer Command

```bash
source /opt/xilinx/xrt/setup.sh
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```
