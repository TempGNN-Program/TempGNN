
````markdown
# TempGNN

**TempGNN** is a target-centric FPGA accelerator for high-performance real-time Temporal Graph Neural Network (TGNN) inference. TempGNN reorganizes temporal graph computation into **Target Dependency Packets (TDPs)**, enabling dependency-driven TDP construction, overlap-aware synchronization, and efficient on-chip execution for irregular, dependency-constrained TGNN workloads.


## Environment Information

The `information/` directory contains the environment information used for the TempGNN artifact.

To regenerate the environment snapshot:

```bash
cd information
bash collect_env.sh
```

The generated `information.txt` records system information, CPU/GPU/FPGA device information, compiler and toolchain versions, Python package versions, Git revision information, and default experimental settings.

## Target Platforms

The main evaluation platform is:

* **FPGA:** Xilinx Alveo U280
* **GPU:** NVIDIA A100 with 80 GB HBM2e
* **CPU:** Intel Xeon Platinum 8357B

## Evaluated Models and Datasets

TempGNN is evaluated on four representative TGNN models:

* JODIE
* TGAT
* TGN
* APAN

and six real-world temporal graph datasets:

* Wikipedia
* MOOC
* Reddit
* LastFM
* WikiTalk
* GDELT

## Default Evaluation Settings

Unless otherwise specified, the default experimental settings are:

* **Precision:** FP32
* **Batch size:** 1000
* **Sampling strategy:** recent sampling

## Citation

Citation information will be added after publication.

## Contact

For questions about the artifact, please contact the authors of the TempGNN paper.

```
```
