ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
BUILD_DIR ?= $(ROOT_DIR)/build/vitis_u280
IP_CACHE_DIR ?= $(BUILD_DIR)/.ipcache
PLATFORM ?= xilinx_u280_xdma_201920_3
TARGET ?= hw
VPP ?= v++
VPP_LINK_FLAGS ?=
VPP_CFLAGS ?=
CXX ?= g++
XILINX_XRT ?= /opt/xilinx/xrt
KERNEL ?= stats
FREQ_HZ ?= 225000000
KERNEL_CLOCK_CUS ?= $(KERNEL_NAME)_1

ifeq ($(KERNEL),forward)
KERNEL_NAME := tempgnn_forward_kernel
KERNEL_SRC := $(ROOT_DIR)/hardware/src/tempgnn_forward_kernel.cpp
KERNEL_XO := $(BUILD_DIR)/tempgnn_forward_kernel.$(TARGET).xo
XCLBIN := $(BUILD_DIR)/tempgnn_forward_kernel.$(TARGET).xclbin
HOST := $(BUILD_DIR)/u280_forward_benchmark_host
HOST_SRC := $(ROOT_DIR)/hardware/host/tempgnn_forward_parallel_xrt_host.cpp
HOST_HEADER := $(ROOT_DIR)/hardware/include/tempgnn_hls.hpp \
	$(ROOT_DIR)/hardware/host/tempgnn_forward_cache_key.hpp
HOST_INCLUDES := -I$(ROOT_DIR)/hardware/include
CFG := $(ROOT_DIR)/hardware/vitis/tempgnn_forward_u280.cfg
HLS_CFG := $(ROOT_DIR)/hardware/vitis/tempgnn_forward_hls.cfg
else
KERNEL_NAME := tempgnn_kernel
KERNEL_SRC := $(ROOT_DIR)/hardware/src/tempgnn_kernel.cpp
KERNEL_XO := $(BUILD_DIR)/tempgnn_kernel.$(TARGET).xo
XCLBIN := $(BUILD_DIR)/tempgnn_kernel.$(TARGET).xclbin
HOST := $(BUILD_DIR)/tempgnn_xrt_host
HOST_SRC := $(ROOT_DIR)/hardware/host/tempgnn_xrt_host.cpp
HOST_HEADER := $(ROOT_DIR)/hardware/include/tempgnn_hls.hpp
HOST_INCLUDES := -I$(ROOT_DIR)/hardware/include
CFG := $(ROOT_DIR)/hardware/vitis/tempgnn_u280.cfg
HLS_CFG := $(ROOT_DIR)/hardware/vitis/tempgnn_hls.cfg
endif

HLS_WORK_DIR := $(BUILD_DIR)/hls_component

.PHONY: all xo xclbin host clean

all: xclbin host

xo: $(KERNEL_XO)

xclbin: $(XCLBIN)

host: $(HOST)

$(BUILD_DIR):
	mkdir -p $@

$(KERNEL_XO): $(KERNEL_SRC) $(ROOT_DIR)/hardware/include/tempgnn_hls.hpp $(HLS_CFG) | $(BUILD_DIR)
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
		--freqhz $(FREQ_HZ):$(KERNEL_CLOCK_CUS) \
		$(VPP_LINK_FLAGS) \
		--config $(CFG) \
		$(KERNEL_XO) -o $@

$(HOST): $(HOST_SRC) $(HOST_HEADER) | $(BUILD_DIR)
	$(CXX) -std=c++17 -O2 -Wall \
		-Wno-unknown-pragmas -Wno-unused-function -Wno-unused-label \
		-I$(XILINX_XRT)/include \
		$(HOST_INCLUDES) \
		$(HOST_SRC) \
		-L$(XILINX_XRT)/lib -lxrt_coreutil -pthread -o $@

clean:
	rm -rf $(BUILD_DIR)
