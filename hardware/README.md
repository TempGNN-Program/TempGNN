# TempGNN Hardware Reproduction

This directory contains the TempGNN hardware path:

- `src/tempgnn_kernel.cpp`: Vitis-HLS kernel implementing recent sampling, TDP expansion, PHLE packet reuse, DDTC/OATS modes, and cycle/memory stats.
- `src/tempgnn_forward_kernel.cpp`: Vitis-HLS kernel that adds a fixed-point TGNN memory-update/embedding forward path on top of TDP construction and PHLE/OATS reuse.
- `tb/tempgnn_tb.cpp`: deterministic C-sim testbench with golden stats for TempGNN, WO/OATS, and WO/DDTC.
- `tb/tempgnn_forward_tb.cpp`: deterministic forward testbench checking the primary DDTC/OATS path, ablation work/memory statistics, and exact repeat consistency across generation-tag wraparound.
- `hls/tempgnn_hls.tcl`: Vitis/Vivado HLS project script for U280, 225 MHz target.
- `hls/tempgnn_forward_hls.tcl`: Vitis/Vivado HLS project script for the full-forward kernel.
- `host/tempgnn_xrt_host.cpp`: XRT host for board execution.
- `vitis/Makefile`: `v++` build for U280 xclbin and host.

Run C-sim without Xilinx tools:

```bash
bash hardware/scripts/run_csim.sh
```

Run the forward C-sim:

```bash
bash hardware/scripts/run_csim.sh forward
```

Run HLS synthesis:

```bash
source /tools/Xilinx/Vitis/2023.2/settings64.sh
bash hardware/scripts/run_hls.sh
```

Run RTL cosim:

```bash
bash hardware/scripts/run_hls.sh cosim
```

Run forward HLS synthesis/cosim:

```bash
bash hardware/scripts/run_hls.sh cosim forward
```

On Windows with Vitis 2025.2 installed at `D:\AMDDesignTools`, call `D:\AMDDesignTools\2025.2\Vitis\settings64.bat` first, then use:

```powershell
$env:TEMPGNN_HLS_PART="xcu55c-fsvh2892-2L-e"
$env:TEMPGNN_HLS_COSIM="1"
vitis-run --mode hls --tcl hardware\hls\tempgnn_hls.tcl
vitis-run --mode hls --tcl hardware\hls\tempgnn_forward_hls.tcl
```

Historical developer-workstation Vitis/Vivado 2025.2 status on June 10, 2026:

- `tempgnn_kernel`: C-sim, C-synthesis, and Verilog RTL cosim all PASS on temporary target `xcu55c-fsvh2892-2L-e`. Estimated clock is 3.244 ns at a 4.444 ns target. Resource estimate is BRAM18 65, DSP 58, FF 19,664, LUT 23,054, URAM 8.
- `tempgnn_forward_kernel`: C-sim, C-synthesis, and Verilog RTL cosim all PASS on the same temporary target. Estimated clock is 3.244 ns. Resource estimate is BRAM18 93, DSP 94, FF 32,422, LUT 39,276, URAM 22.

Those U55C-targeted results are development checks only and are not the
packaged FPGA evidence. The reviewer artifact contains separately built U280
xclbins, post-route reports, and board measurements under `artifacts/u280/` and
`results/reviewer_u280_runs/`. The exact measured environment is recorded in
`ENVIRONMENT.md`.

Build for U280:

```bash
source /tools/Xilinx/Vitis/2023.2/settings64.sh
make u280-build \
  U280_PLATFORM=/opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
```

Run the reviewer-facing four-implementation preflight and real-input
measurement workflow:

```bash
source /opt/xilinx/xrt/setup.sh
make u280-core-preflight
make ae-core-u280 U280_CORE_DEVICE=0 U280_CORE_REPETITIONS=3
```

The independent MATG, ViTeGNN, and RTGA sources, mechanism map, build commands,
and scope limits are documented in `baselines/README.md`.
