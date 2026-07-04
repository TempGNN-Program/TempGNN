ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
BUILD_DIR ?= $(ROOT_DIR)/build/vitis_u280
PLATFORM ?= xilinx_u280_xdma_201920_3
TARGET ?= hw
VPP ?= v++
VPP_LINK_FLAGS ?=
VPP_CFLAGS ?=
CXX ?= g++
XILINX_XRT ?= /opt/xilinx/xrt
KERNEL ?= stats

ifeq ($(KERNEL),forward)
KERNEL_NAME := tempgnn_forward_kernel
KERNEL_SRC := $(ROOT_DIR)/hardware/src/tempgnn_forward_kernel.cpp
KERNEL_XO := $(BUILD_DIR)/tempgnn_forward_kernel.$(TARGET).xo
XCLBIN := $(BUILD_DIR)/tempgnn_forward_kernel.$(TARGET).xclbin
HOST := $(BUILD_DIR)/tempgnn_forward_xrt_host
HOST_SRC := $(ROOT_DIR)/hardware/host/tempgnn_forward_xrt_host.cpp
CFG := $(ROOT_DIR)/hardware/vitis/tempgnn_forward_u280.cfg
else
KERNEL_NAME := tempgnn_kernel
KERNEL_SRC := $(ROOT_DIR)/hardware/src/tempgnn_kernel.cpp
KERNEL_XO := $(BUILD_DIR)/tempgnn_kernel.$(TARGET).xo
XCLBIN := $(BUILD_DIR)/tempgnn_kernel.$(TARGET).xclbin
HOST := $(BUILD_DIR)/tempgnn_xrt_host
HOST_SRC := $(ROOT_DIR)/hardware/host/tempgnn_xrt_host.cpp
CFG := $(ROOT_DIR)/hardware/vitis/tempgnn_u280.cfg
endif

.PHONY: all xclbin host clean

all: xclbin host

xclbin: $(XCLBIN)

host: $(HOST)

$(BUILD_DIR):
	mkdir -p $@

$(KERNEL_XO): $(KERNEL_SRC) $(ROOT_DIR)/hardware/include/tempgnn_hls.hpp | $(BUILD_DIR)
	$(VPP) -c -t $(TARGET) --platform $(PLATFORM) \
		-k $(KERNEL_NAME) \
		-I$(ROOT_DIR)/hardware/include \
		$(VPP_CFLAGS) \
		$(KERNEL_SRC) -o $@

$(XCLBIN): $(KERNEL_XO) $(CFG)
	$(VPP) -l -t $(TARGET) --platform $(PLATFORM) \
		$(VPP_LINK_FLAGS) \
		--config $(CFG) \
		$(KERNEL_XO) -o $@

$(HOST): $(HOST_SRC) $(ROOT_DIR)/hardware/include/tempgnn_hls.hpp | $(BUILD_DIR)
	$(CXX) -std=c++17 -O2 -Wall \
		-I$(XILINX_XRT)/include \
		-I$(ROOT_DIR)/hardware/include \
		$(HOST_SRC) \
		-L$(XILINX_XRT)/lib -lxrt_coreutil -pthread -o $@

clean:
	rm -rf $(BUILD_DIR)
