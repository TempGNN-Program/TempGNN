# TempGNN AE Reproduction Report

## Scope

The CPU-only command regenerates paper-reference CSV/SVG records from a source-labeled table; it does not rerun CPU, GPU, or FPGA baselines. The fresh U280 command executes four distinct xclbins and writes new latency, total-board-power, checksum, and provenance evidence. MATG, ViTeGNN, and RTGA are independent paper-based forward-path reproductions, not the baseline authors' complete original stacks.
The fresh command is a bounded mechanism-level comparison on real-dataset prefixes. Each xclbin link request is cross-checked against the Vivado-connected kernel clock and nonnegative post-route WNS/TNS; unequal timing-closed clocks block normalized comparison generation. It is not paper-equivalent: the packaged kernels use an 8-dimensional Q10 forward path and `xbutil` board power, while the paper specifies full models, default 32-bit floating point, full evaluation streams, and post-route Vivado power estimates.

See `AE_APPENDIX_DRAFT.md` for the authoritative measurement boundary.

## Packaged Reference Averages

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

Latest run: none

No fresh four-system run is packaged yet.

A numerical tolerance PASS does not establish the Results Reproduced bridge while provenance marks the method as not paper-equivalent. Reference CSV values are never substituted for measured rows.

## Hardware

All four comparison builds request 225 MHz on `xilinx_u280_gen3x16_xdma_1_202211_1`.
The original TempGNN sanity build reports WNS=0.016 ns and TNS=0.0 ns.

## Commands

```bash
python3 -m unittest discover -s tests
python3 -m scripts.reproduce_paper_figures
make baseline-csim
make u280-core-preflight
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```
