# Baseline Reproduction Notes

## TempGNN
- Platform: Xilinx Alveo U280
- Toolchain: Xilinx Vitis 2023.2
- Reproduction status: Runnable U280 implementation with XRT host and measurement workflow.
- Key settings: Forward-path accelerator
- Notes: Run with make ae-core-u280.

## MATG
- Platform: Xilinx Alveo U280
- Toolchain: Independent Vitis-HLS 2023.2 reproduction informed by the MATG paper
- Reproduction status: Independent paper-based U280 forward-path reproduction.
- Key settings: Neighbor pruning and LUT time encoding
- Notes: Run with make ae-core-u280.

## ViTeGNN
- Platform: Xilinx Alveo U280
- Toolchain: Independent Vitis-HLS 2023.2 reproduction informed by the ViTeGNN paper
- Reproduction status: Independent paper-based U280 forward-path reproduction.
- Key settings: Lightweight attention and retained-neighbor processing
- Notes: Run with make ae-core-u280.

## RTGA
- Platform: Xilinx Alveo U280
- Toolchain: Independent Vitis-HLS 2023.2 reproduction informed by the RTGA paper
- Reproduction status: Independent paper-based U280 forward-path reproduction.
- Key settings: Temporal-tree scheduling and temporal-aware caching
- Notes: Run with make ae-core-u280.

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
