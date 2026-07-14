ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../..)
SYSTEM ?= MATG
TARGET ?= hw
PLATFORM ?= /opt/xilinx/platforms/xilinx_u280_gen3x16_xdma_1_202211_1/xilinx_u280_gen3x16_xdma_1_202211_1.xpfm
VPP ?= v++
CXX ?= g++
XILINX_XRT ?= /opt/xilinx/xrt
FREQ_HZ ?= 225000000

SYSTEM_LOWER := $(shell echo $(SYSTEM) | tr A-Z a-z)
BUILD_DIR ?= $(ROOT_DIR)/build/baselines/$(SYSTEM_LOWER)_$(TARGET)
IP_CACHE_DIR ?= $(BUILD_DIR)/.ipcache

ifeq ($(SYSTEM),MATG)
KERNEL_NAME := matg_kernel
else ifeq ($(SYSTEM),ViTeGNN)
KERNEL_NAME := vitegnn_kernel
else ifeq ($(SYSTEM),RTGA)
KERNEL_NAME := rtga_kernel
else
$(error SYSTEM must be MATG, ViTeGNN, or RTGA)
endif

KERNEL_SRC := $(ROOT_DIR)/hardware/baselines/src/$(KERNEL_NAME).cpp
KERNEL_XO := $(BUILD_DIR)/$(KERNEL_NAME).$(TARGET).xo
XCLBIN := $(BUILD_DIR)/$(KERNEL_NAME).$(TARGET).xclbin
CFG := $(ROOT_DIR)/hardware/baselines/vitis/$(KERNEL_NAME)_u280.cfg
HLS_CFG := $(ROOT_DIR)/hardware/baselines/vitis/$(KERNEL_NAME)_hls.cfg
HLS_WORK_DIR := $(BUILD_DIR)/hls_component
HOST_SRC := $(ROOT_DIR)/hardware/baselines/host/u280_forward_benchmark_host.cpp
HOST := $(BUILD_DIR)/u280_forward_benchmark_host
CSIM := $(BUILD_DIR)/baseline_csim
CSIM_SRC := $(ROOT_DIR)/hardware/baselines/tb/baseline_csim.cpp

.PHONY: all xo xclbin host csim clean

all: xclbin host

xo: $(KERNEL_XO)

xclbin: $(XCLBIN)

host: $(HOST)

csim: $(CSIM)

$(BUILD_DIR):
	mkdir -p $@

$(KERNEL_XO): $(KERNEL_SRC) $(ROOT_DIR)/hardware/baselines/include/baseline_hls.hpp $(HLS_CFG) | $(BUILD_DIR)
	$(VPP) -c --mode hls \
		--platform $(PLATFORM) \
		--freqhz $(FREQ_HZ) \
		--config $(HLS_CFG) \
		--work_dir $(HLS_WORK_DIR)
	cp $(HLS_WORK_DIR)/$(KERNEL_NAME).xo $@

$(XCLBIN): $(KERNEL_XO) $(CFG)
	$(VPP) -l -t $(TARGET) --platform $(PLATFORM) \
		--temp_dir $(BUILD_DIR)/_x \
		--remote_ip_cache $(IP_CACHE_DIR) \
		--freqhz $(FREQ_HZ):$(KERNEL_NAME)_1 \
		--config $(CFG) \
		$(KERNEL_XO) -o $@

$(HOST): $(HOST_SRC) $(ROOT_DIR)/hardware/baselines/include/baseline_hls.hpp | $(BUILD_DIR)
	$(CXX) -std=c++17 -O2 -Wall \
		-Wno-unknown-pragmas -Wno-unused-function -Wno-unused-label \
		-I$(XILINX_XRT)/include \
		-I$(ROOT_DIR)/hardware/baselines/include \
		$(HOST_SRC) \
		-L$(XILINX_XRT)/lib -lxrt_coreutil -pthread -o $@

$(CSIM): $(CSIM_SRC) $(ROOT_DIR)/hardware/baselines/src/matg_kernel.cpp \
		$(ROOT_DIR)/hardware/baselines/src/vitegnn_kernel.cpp \
		$(ROOT_DIR)/hardware/baselines/src/rtga_kernel.cpp \
		$(ROOT_DIR)/hardware/baselines/include/baseline_hls.hpp | $(BUILD_DIR)
	$(CXX) -std=c++17 -O2 -Wall \
		-Wno-unknown-pragmas -Wno-unused-function -Wno-unused-label \
		-I$(ROOT_DIR)/hardware/baselines/include \
		$(CSIM_SRC) \
		$(ROOT_DIR)/hardware/baselines/src/matg_kernel.cpp \
		$(ROOT_DIR)/hardware/baselines/src/vitegnn_kernel.cpp \
		$(ROOT_DIR)/hardware/baselines/src/rtga_kernel.cpp -o $@

clean:
	rm -rf $(BUILD_DIR)
