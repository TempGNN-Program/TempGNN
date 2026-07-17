PYTHON ?= python3
Q14_DATASETS ?= WIKI MOOC REDDIT
Q14_MODELS ?= JODIE TGAT TGN APAN
Q14_OUT ?= results/q14_real_tgl_edges
AE_OUT ?= results/ae_report
BOARD_JSON ?= results/board_u280/summary.json
U280_BUILD_PROVENANCE ?= artifacts/u280/TempGNN/evidence/build_provenance.json

U280_PLATFORM ?= xilinx_u280_gen3x16_xdma_1_202211_1
U280_BUILD_DIR ?= $(CURDIR)/build/vitis_u280_forward_hw
U280_FORWARD_FREQ_HZ ?= 168000000
U280_FORWARD_CFG ?= $(CURDIR)/hardware/vitis/tempgnn_forward_u280_21cu.cfg
U280_FORWARD_CLOCK_CUS ?= tempgnn_forward_kernel_1,tempgnn_forward_kernel_2,tempgnn_forward_kernel_3,tempgnn_forward_kernel_4,tempgnn_forward_kernel_5,tempgnn_forward_kernel_6,tempgnn_forward_kernel_7,tempgnn_forward_kernel_8,tempgnn_forward_kernel_9,tempgnn_forward_kernel_10,tempgnn_forward_kernel_11,tempgnn_forward_kernel_12,tempgnn_forward_kernel_13,tempgnn_forward_kernel_14,tempgnn_forward_kernel_15,tempgnn_forward_kernel_16,tempgnn_forward_kernel_17,tempgnn_forward_kernel_18,tempgnn_forward_kernel_19,tempgnn_forward_kernel_20,tempgnn_forward_kernel_21
U280_XCLBIN ?= artifacts/u280/TempGNN/bin/tempgnn_forward_kernel.hw.xclbin
U280_HOST ?= artifacts/u280/TempGNN/bin/u280_forward_benchmark_host
U280_FIXTURE ?= results/fixtures/forward_maxbatch
U280_DEVICE ?= 0
U280_LAYOUT_CELLS ?= results/board_u280/layout_hook/tempgnn_u280_routed_cells.csv
U280_LAYOUT_OUTDIR ?= $(CURDIR)/results/board_u280/layout_hook
U280_CORE_CONFIG ?= configs/u280_core_reproduction.json
U280_CORE_OUT ?= results/reviewer_u280_runs
U280_CORE_DEVICE ?= 0
U280_CORE_REPETITIONS ?= 3
U280_CORE_MATCH_FLAG ?=
U280_STAGE_HOST ?= build/baselines/matg_hw/u280_forward_benchmark_host
U280_STAGE_TEMPGNN_HOST ?= $(U280_STAGE_TEMPGNN_BUILD)/u280_forward_benchmark_host
U280_STAGE_REFERENCE ?= build/baselines/matg_hw/baseline_csim
U280_STAGE_VALIDATION_LOG ?= build/baseline_csim_real24.log
U280_STAGE_TEMPGNN_BUILD ?= $(U280_BUILD_DIR)
U280_STAGE_MATG_BUILD ?= build/baselines/matg_hw
U280_STAGE_VITEGNN_BUILD ?= build/baselines/vitegnn_hw
U280_STAGE_RTGA_BUILD ?= build/baselines/rtga_hw
U280_STAGE_TEMPGNN_LOG ?= build/tempgnn_final_build.log
U280_STAGE_MATG_LOG ?= build/matg_final_build.log
U280_STAGE_VITEGNN_LOG ?= build/vitegnn_final_build.log
U280_STAGE_RTGA_LOG ?= build/rtga_final_build.log

AE_PACKAGE ?= ae_export/pap142_tempgnn_sc26_ae_u280.tgz

.PHONY: help smoke test figures data q14 report all package \
	baseline-csim u280-build u280-baseline-build u280-run u280-layout \
	u280-stage-artifacts u280-core-preflight ae-core-u280 \
	ae-core-u280-strict \
	release-preflight release-preflight-results \
	clean-ae

help:
	@echo "TempGNN AE targets"
	@echo "  make figures     - generate CSV/SVG figures from results/result.csv"
	@echo "  make smoke       - run unit tests and generate figures from results/result.csv"
	@echo "  make data        - download TGL edge streams for Q14 (WIKI/MOOC/REDDIT by default)"
	@echo "  make q14         - run real edge-stream OATS/Q14 profiling"
	@echo "  make baseline-csim - compile and run the three paper-based baseline kernels on a generated fixture"
	@echo "  make report      - regenerate AE_README, runbook, inventory, and summary"
	@echo "  make all         - optional software checks and report (no performance baselines)"
	@echo "  make u280-build  - build U280 forward xclbin and XRT host when U280 platform exists"
	@echo "  make u280-baseline-build - build distinct MATG/ViTeGNN/RTGA U280 xclbins and common host"
	@echo "  make u280-stage-artifacts - stage anonymized xclbins and post-route provenance"
	@echo "  make u280-run    - run prebuilt/built U280 xclbin on a U280 board"
	@echo "  make u280-layout - render FPGA layout image from routed U280 LOC export"
	@echo "  make u280-core-preflight - verify four distinct reviewer-runnable U280 implementations"
	@echo "  make ae-core-u280 - one-click U280 validation plus paper/core figure generation"
	@echo "  make ae-core-u280-strict - additionally require numerical paper-figure tolerance PASS"
	@echo "  make release-preflight - require license, DOI metadata, distinct U280 artifacts, and a complete fresh run"
	@echo "  make release-preflight-results - additionally require paper-equivalent scope and tolerance PASS"
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

report:
	$(PYTHON) -m scripts.make_ae_report \
		--q14-summary $(Q14_OUT)/q14_dataset_model_summary.csv \
		--board-json $(BOARD_JSON) \
		--build-provenance $(U280_BUILD_PROVENANCE) \
		--out $(AE_OUT)

all: smoke report

baseline-csim:
	$(PYTHON) scripts/generate_u280_comparison_fixture.py \
		--dataset WK --model TGN --batch-size 32 \
		--synthetic \
		--output build/baseline_csim_fixture
	$(MAKE) -C hardware/baselines/vitis SYSTEM=MATG csim
	build/baselines/matg_hw/baseline_csim build/baseline_csim_fixture 10 1 1 1 all --write

u280-build:
	mkdir -p build
	bash -o pipefail -c '$(MAKE) -C hardware/vitis \
		KERNEL=forward \
		PLATFORM="$(U280_PLATFORM)" \
		TARGET=hw \
		BUILD_DIR="$(U280_BUILD_DIR)" \
		FREQ_HZ="$(U280_FORWARD_FREQ_HZ)" \
		CFG="$(U280_FORWARD_CFG)" \
		KERNEL_CLOCK_CUS="$(U280_FORWARD_CLOCK_CUS)" \
		xclbin host 2>&1 | tee build/tempgnn_final_build.log'

u280-baseline-build:
	mkdir -p build
	bash -o pipefail -c '$(MAKE) -C hardware/baselines/vitis SYSTEM=MATG TARGET=hw all \
		2>&1 | tee build/matg_final_build.log'
	bash -o pipefail -c '$(MAKE) -C hardware/baselines/vitis SYSTEM=ViTeGNN TARGET=hw all \
		2>&1 | tee build/vitegnn_final_build.log'
	bash -o pipefail -c '$(MAKE) -C hardware/baselines/vitis SYSTEM=RTGA TARGET=hw all \
		2>&1 | tee build/rtga_final_build.log'

u280-stage-artifacts:
	$(PYTHON) -m scripts.stage_u280_artifacts \
		--build TempGNN=$(U280_STAGE_TEMPGNN_BUILD) \
		--build MATG=$(U280_STAGE_MATG_BUILD) \
		--build ViTeGNN=$(U280_STAGE_VITEGNN_BUILD) \
		--build RTGA=$(U280_STAGE_RTGA_BUILD) \
		--build-log TempGNN=$(U280_STAGE_TEMPGNN_LOG) \
		--build-log MATG=$(U280_STAGE_MATG_LOG) \
		--build-log ViTeGNN=$(U280_STAGE_VITEGNN_LOG) \
		--build-log RTGA=$(U280_STAGE_RTGA_LOG) \
		--host $(U280_STAGE_HOST) \
		--system-host TempGNN=$(U280_STAGE_TEMPGNN_HOST) \
		--baseline-reference $(U280_STAGE_REFERENCE) \
		--baseline-validation-log $(U280_STAGE_VALIDATION_LOG)

u280-run:
	mkdir -p results/board_u280
	$(U280_HOST) $(U280_XCLBIN) $(U280_FIXTURE) tempgnn_forward_kernel \
		20 2 16 1 1 $(U280_DEVICE) 1 1 \
		2>&1 | tee results/board_u280/forward_maxbatch.log

u280-layout:
	$(PYTHON) -m scripts.render_fpga_layout \
		--cells $(U280_LAYOUT_CELLS) \
		--summary $(BOARD_JSON) \
		--out-png results/board_u280/tempgnn_u280_fpga_layout.png \
		--out-svg results/board_u280/tempgnn_u280_fpga_layout.svg

u280-core-preflight:
	$(PYTHON) -m scripts.run_u280_core_reproduction \
		--config $(U280_CORE_CONFIG) \
		--preflight-only

ae-core-u280: figures
	$(PYTHON) -m scripts.run_u280_core_reproduction \
		--config $(U280_CORE_CONFIG) \
		--out $(U280_CORE_OUT) \
		--device $(U280_CORE_DEVICE) \
		--repetitions $(U280_CORE_REPETITIONS) $(U280_CORE_MATCH_FLAG)
	$(MAKE) report

ae-core-u280-strict:
	$(MAKE) ae-core-u280 U280_CORE_MATCH_FLAG=--require-paper-match

release-preflight:
	$(PYTHON) -m scripts.check_release_readiness \
		--config $(U280_CORE_CONFIG) \
		--runs $(U280_CORE_OUT)

release-preflight-results:
	$(PYTHON) -m scripts.check_release_readiness \
		--config $(U280_CORE_CONFIG) \
		--runs $(U280_CORE_OUT) \
		--require-results-reproduced

package: figures report
	bash scripts/package_ae.sh $(AE_PACKAGE)

clean-ae:
	rm -rf results/ae_report results/paper_reproduction results/q14_real_tgl_edges results/reviewer_u280_runs
