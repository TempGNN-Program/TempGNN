# TempGNN Hardware Reproduction

This directory contains the TempGNN hardware path:

- `src/tempgnn_kernel.cpp`: Vitis-HLS kernel implementing recent sampling, TDP expansion, PHLE packet reuse, DDTC/OATS modes, and cycle/memory stats.
- `src/tempgnn_forward_kernel.cpp`: Vitis-HLS kernel that adds a fixed-point TGNN memory-update/embedding forward path on top of TDP construction and PHLE/OATS reuse.
- `tb/tempgnn_tb.cpp`: deterministic C-sim testbench with golden stats for TempGNN, WO/OATS, and WO/DDTC.
- `tb/tempgnn_forward_tb.cpp`: deterministic forward testbench checking that DDTC/OATS ablations preserve target embeddings while changing work/memory stats.
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
source /path/to/Xilinx/Vitis/2019.2/settings64.sh
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

Local Vitis/Vivado 2025.2 status on June 10, 2026:

- `tempgnn_kernel`: C-sim, C-synthesis, and Verilog RTL cosim all PASS on temporary target `xcu55c-fsvh2892-2L-e`. Estimated clock is 3.244 ns at a 4.444 ns target. Resource estimate is BRAM18 65, DSP 58, FF 19,664, LUT 23,054, URAM 8.
- `tempgnn_forward_kernel`: C-sim, C-synthesis, and Verilog RTL cosim all PASS on the same temporary target. Estimated clock is 3.244 ns. Resource estimate is BRAM18 93, DSP 94, FF 32,422, LUT 39,276, URAM 22.

The local installer does not currently include the U280 device/platform used by the paper, so these are synthesizability and RTL-cosim results rather than final paper-equivalent U280 implementation numbers.

Build for U280:

```bash
make -C hardware/vitis PLATFORM=xilinx_u280_xdma_201920_3 TARGET=hw all
```

Generate board input arrays:

```bash
python -m scripts.export_hardware_fixture --events 8192 --target-events 1024 --out results/hardware_fixture
```

Run the board host:

```bash
build/vitis_u280/tempgnn_xrt_host build/vitis_u280/tempgnn_kernel.hw.xclbin results/hardware_fixture
```
