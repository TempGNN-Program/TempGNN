# TempGNN

**TempGNN** is a target-centric FPGA accelerator for high-performance real-time Temporal Graph Neural Network (TGNN) inference. TempGNN reorganizes temporal graph computation into **Target Dependency Packets (TDPs)**, enabling dependency-driven TDP construction, overlap-aware synchronization, and efficient on-chip execution for irregular, dependency-constrained TGNN workloads.

## Overview

Temporal Graph Neural Networks are effective for modeling dynamic graphs with evolving topology and temporal interactions. However, high-performance TGNN inference is challenging because strict temporal dependencies in vertex-memory updates force timestamp-ordered execution, leading to limited useful parallelism and inefficient off-chip memory communication.

TempGNN addresses these challenges through:

- **Target Dependency Packets (TDPs):** a target-centric abstraction that captures the temporally valid dependency states required for each target update.
- **Dependency-driven TDP construction:** a data-loading and construction pipeline that integrates timestamp-constrained temporal sampling with on-the-fly dependency expansion.
- **Overlap-aware synchronization:** a packet-level synchronization strategy that detects shared dependency packets across overlapping targets and reduces redundant dependency processing.
- **FPGA-based acceleration:** an implementation on the Xilinx Alveo U280 platform for low-latency and energy-efficient real-time TGNN inference.

## Artifact Status

Code will be made available soon.

This repository currently provides artifact-related information for the TempGNN submission, including environment information and reproducibility notes. Full source code, build scripts, dataset preprocessing scripts, and evaluation scripts will be released in a future update.

## Repository Structure

```text
TempGNN/
├── information/
│   ├── README.md
│   ├── collect_env.sh
│   └── information.txt
└── README.md
## Environment Information

The information/ directory contains the environment information used for the TempGNN artifact.

To regenerate the environment snapshot:

cd information
bash collect_env.sh

The generated information.txt records system information, CPU/GPU/FPGA device information, compiler and toolchain versions, Python package versions, Git revision information, and default experimental settings.

Target Platforms

The main evaluation platform is:

FPGA: Xilinx Alveo U280
GPU: NVIDIA A100 with 80 GB HBM2e
CPU: Intel Xeon Platinum 8357B
Evaluated Models and Datasets

TempGNN is evaluated on four representative TGNN models:

JODIE
TGAT
TGN
APAN

and six real-world temporal graph datasets:

Wikipedia
MOOC
Reddit
LastFM
WikiTalk
GDELT
Default Evaluation Settings

Unless otherwise specified, the default experimental settings are:

Precision: FP32
Batch size: 1000
Sampling strategy: recent sampling
Citation

Citation information will be added after publication.

Contact

For questions about the artifact, please contact the authors of the TempGNN paper.
