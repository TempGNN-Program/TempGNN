# Baseline Reproduction Notes

## TempGNN
- Platform: Xilinx Alveo U280, 2x4 GB HBM2, 460 GB/s
- Toolchain: Xilinx Vitis, 225 MHz post-route target
- Reproduction status: This repo provides the Vitis-HLS kernel, C-sim/cosim scripts, XRT host, U280 v++ build flow, and measured U280 board evidence.
- Key settings: batch size 1000, recent sampling, JODIE/TGN/TGAT/APAN, 32-bit floating point
- Notes: Primary TempGNN comparison row.

## MATG
- Platform: Xilinx Alveo U280 after reproduction
- Toolchain: Xilinx Vitis 2020.2
- Reproduction status: Reproduced from the published paper and available public source, then measured on U280 as a comparison input.
- Key settings: TGN-attn model-architecture co-design with simplified attention, LUT time encoder, neighbor pruning, knowledge distillation
- Notes: FPGA baseline comparison row measured from the reproduced U280 run.

## ViTeGNN
- Platform: Xilinx Alveo U280
- Toolchain: Xilinx Vitis 2022.2
- Reproduction status: Reproduced according to the published paper, then measured on U280 as a comparison input.
- Key settings: ViTeGNN-lat/bal/thpt modes; TGN-attn hidden/memory/time dim 100; batch sizes 50/200/200; 4 remaining neighbors
- Notes: FPGA baseline comparison row measured from the reproduced U280 run.

## RTGA
- Platform: Xilinx Alveo U280
- Toolchain: Xilinx Vivado 2019.1
- Reproduction status: Reproduced according to the published paper, then measured on U280 as a comparison input.
- Key settings: 8 TAUs; temporal tree construction/update, redundancy-aware sampling, temporal-aware data caching
- Notes: FPGA baseline comparison row measured from the reproduced U280 run.

## Cascade
- Platform: NVIDIA A100 GPU
- Toolchain: CUDA
- Reproduction status: Reproduced according to the published paper, then measured in the GPU comparison environment.
- Key settings: Dependency-aware batching GPU software baseline.
- Notes: GPU baseline comparison row measured from the reproduced run.

## TGLite-CPU
- Platform: 32-core Intel Xeon Platinum 8357B, 2.6 GHz, 503 GB DDR4, 16 memory channels
- Toolchain: TGLite artifact / CPU baseline
- Reproduction status: Reproduced from the released artifact, then measured in the CPU comparison environment.
- Key settings: batch size 1000, recent sampling
- Notes: CPU normalization baseline measured from the reproduced run.
