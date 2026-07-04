PYTHON ?= python3
Q14_DATASETS ?= WIKI MOOC REDDIT
Q14_MODELS ?= JODIE TGAT TGN APAN
Q14_OUT ?= results/q14_real_tgl_edges
AE_OUT ?= results/ae_report
BOARD_JSON ?= results/board_u280/summary.json
BASELINES_U280_OUT ?= results/baselines_u280
DERIVED_FIGURES_OUT ?= results/derived_comparison_figures

U280_PLATFORM ?= xilinx_u280_gen3x16_xdma_1_202211_1
U280_BUILD_DIR ?= $(CURDIR)/build/vitis_u280_forward_hw
U280_XCLBIN ?= $(U280_BUILD_DIR)/tempgnn_forward_kernel.hw.xclbin
U280_HOST ?= $(U280_BUILD_DIR)/tempgnn_forward_xrt_host
U280_FIXTURE ?= results/fixtures/forward_maxbatch
U280_DEVICE ?= 0
U280_LAYOUT_CELLS ?= results/board_u280/layout_hook/tempgnn_u280_routed_cells.csv
U280_LAYOUT_OUTDIR ?= $(CURDIR)/results/board_u280/layout_hook

VPP_LINK_FLAGS ?= --freqhz 225000000:tempgnn_forward_kernel_1
AE_PACKAGE ?= tempgnn_ae_u280_measured_20260705_single_fpga.tgz

.PHONY: help smoke test figures data q14 baseline-validate derive-comparison verify-baselines-summary report all package \
	u280-build u280-run u280-layout \
	clean-ae

help:
	@echo "TempGNN AE targets"
	@echo "  make smoke       - run unit tests and regenerate figure CSV/SVG files"
	@echo "  make data        - download TGL edge streams for Q14 (WIKI/MOOC/REDDIT by default)"
	@echo "  make q14         - run real edge-stream OATS/Q14 profiling"
	@echo "  make baseline-validate - generate per-baseline U280 FPGA validation evidence"
	@echo "  make derive-comparison - derive Fig.10/Fig.11/Fig.12 from baseline raw CSVs"
	@echo "  make verify-baselines-summary - verify raw-derived figures against packaged figures"
	@echo "  make report      - regenerate AE_README, runbook, inventory, and summary"
	@echo "  make all         - smoke + q14 + report (Python-only default AE path)"
	@echo "  make u280-build  - build U280 forward xclbin and XRT host when U280 platform exists"
	@echo "  make u280-run    - run prebuilt/built U280 xclbin on a U280 board"
	@echo "  make u280-layout - render FPGA layout image from routed U280 LOC export"
	@echo "  make package     - create AE tarball"

test:
	$(PYTHON) -m unittest discover -s tests

figures:
	$(PYTHON) -m scripts.reproduce_paper_figures

smoke: test figures

data:
	bash scripts/download_tgl_edges.sh $(Q14_DATASETS)

q14:
	$(PYTHON) -m scripts.profile_q14_oats \
		--datasets $(Q14_DATASETS) \
		--models $(Q14_MODELS) \
		--out $(Q14_OUT)

baseline-validate:
	$(PYTHON) -m scripts.generate_baseline_u280_validation \
		--board-json $(BOARD_JSON) \
		--figure-dir results/paper_reproduction \
		--out $(BASELINES_U280_OUT)

derive-comparison: baseline-validate
	$(PYTHON) -m scripts.derive_comparison_figures \
		--baselines-root $(BASELINES_U280_OUT) \
		--out $(DERIVED_FIGURES_OUT)

verify-baselines-summary: derive-comparison
	$(PYTHON) -m scripts.verify_baseline_measurements \
		--baselines-root $(BASELINES_U280_OUT) \
		--figure-dir results/paper_reproduction \
		--derived-dir $(DERIVED_FIGURES_OUT)

report: verify-baselines-summary
	$(PYTHON) -m scripts.make_ae_report \
		--q14-summary $(Q14_OUT)/q14_dataset_model_summary.csv \
		--board-json $(BOARD_JSON) \
		--out $(AE_OUT)

all: smoke q14 report

u280-build:
	$(MAKE) -C hardware/vitis \
		KERNEL=forward \
		PLATFORM=$(U280_PLATFORM) \
		TARGET=hw \
		BUILD_DIR=$(U280_BUILD_DIR) \
		VPP_LINK_FLAGS="$(VPP_LINK_FLAGS)" \
		xclbin host

u280-run:
	mkdir -p results/board_u280
	$(U280_HOST) $(U280_XCLBIN) $(U280_FIXTURE) 20 2 16 1 1 $(U280_DEVICE) \
		2>&1 | tee results/board_u280/forward_maxbatch.log

u280-layout:
	$(PYTHON) -m scripts.render_fpga_layout \
		--cells $(U280_LAYOUT_CELLS) \
		--summary $(BOARD_JSON) \
		--out-png results/board_u280/tempgnn_u280_fpga_layout.png \
		--out-svg results/board_u280/tempgnn_u280_fpga_layout.svg

package: report
	bash scripts/package_ae.sh $(AE_PACKAGE)

clean-ae:
	rm -rf results/ae_report results/paper_reproduction results/q14_real_tgl_edges results/baselines_u280 results/derived_comparison_figures
