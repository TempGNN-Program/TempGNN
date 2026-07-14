# Baseline Reproduction Notes

## TempGNN
- Platform: Xilinx Alveo U280
- Toolchain: Xilinx Vitis 2023.2 for the packaged AE path; paper target 225 MHz
- Reproduction status: The repository supplies a bounded Q10 forward-path implementation, XRT host, build flow, and fresh U280 measurement harness. It is not the complete paper implementation.
- Key settings: 8-dimensional Q10 diagnostic path; batch-size-1000 real-stream prefixes in the U280 workflow
- Notes: Paper reference figures and fresh U280 diagnostic measurements are stored in separate directories.

## MATG
- Platform: Xilinx Alveo U280
- Toolchain: Clean-room Vitis-HLS 2023.2 reproduction informed by the MATG paper
- Reproduction status: Independent bounded implementation of the documented MATG-style pruning and LUT time-encoding mechanisms; freshly runnable on U280, but not the authors' complete stack or a paper-equivalent rerun.
- Key settings: bounded degree scan, neighbor pruning, LUT time encoding, fixed-point forward path
- Notes: Its measured rows are generated only by the fresh U280 workflow, never copied into reference figures.

## ViTeGNN
- Platform: Xilinx Alveo U280
- Toolchain: Clean-room Vitis-HLS 2023.2 reproduction informed by the ViTeGNN paper
- Reproduction status: Independent bounded implementation of documented lightweight-attention and retained-neighbor mechanisms; freshly runnable on U280, but not the authors' complete lat/bal/thpt stack.
- Key settings: four retained neighbors, lightweight attention, fixed-point forward path
- Notes: Its measured rows are generated only by the fresh U280 workflow, never copied into reference figures.

## RTGA
- Platform: Xilinx Alveo U280
- Toolchain: Clean-room Vitis-HLS 2023.2 reproduction informed by the RTGA paper
- Reproduction status: Independent bounded implementation of documented temporal-tree scheduling and temporal-aware caching mechanisms; freshly runnable on U280, but not the authors' complete stack.
- Key settings: temporal-tree traversal, redundancy-aware selection, temporal-aware cache, fixed-point path
- Notes: Its measured rows are generated only by the fresh U280 workflow, never copied into reference figures.

## Cascade
- Platform: NVIDIA A100 GPU in the paper
- Toolchain: CUDA reference baseline
- Reproduction status: Reference-figure input only; this repository does not execute Cascade on U280.
- Key settings: dependency-aware GPU batching
- Notes: Cascade is not one of the fresh U280 xclbins.

## TGLite-CPU
- Platform: 32-core Intel Xeon Platinum 8357B in the paper
- Toolchain: TGLite CPU reference baseline
- Reproduction status: Reference-figure input only; this repository does not freshly execute TGLite-CPU.
- Key settings: batch size 1000 and recent sampling in the paper configuration
- Notes: Reference-only plotting input.
