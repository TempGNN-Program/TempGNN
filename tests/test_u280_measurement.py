from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from array import array
from pathlib import Path

from scripts.measure_u280_forward import (
    kernel_scalar_arguments,
    parse_host_output,
    parse_post_route_timing,
    parse_vivado_kernel_clock,
    parse_xclbin_link_requested_frequency,
    portable_command,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class U280FixtureTests(unittest.TestCase):
    def test_fixture_generation_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first"
            second = Path(temp_dir) / "second"
            for output in (first, second):
                subprocess.run(
                    [
                        sys.executable,
                        str(REPO_ROOT / "scripts/generate_u280_comparison_fixture.py"),
                        "--dataset",
                        "WK",
                        "--model",
                        "TGN",
                        "--batch-size",
                        "8",
                        "--synthetic",
                        "--output",
                        str(output),
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    text=True,
                )
            first_metadata = json.loads((first / "metadata.json").read_text(encoding="utf-8"))
            second_metadata = json.loads((second / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(first_metadata["files_sha256"], second_metadata["files_sha256"])
            self.assertEqual(first_metadata["input_kind"], "synthetic_smoke")
            self.assertEqual(first_metadata["num_targets"], 8)
            self.assertEqual(first_metadata["history_entries"], first_metadata["num_events"] * 2)
            for name, expected_hash in first_metadata["files_sha256"].items():
                self.assertEqual(sha256(first / name), expected_hash)

    def test_real_fixture_compacts_and_records_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sample = root / "sample" / "edges.csv"
            sample.parent.mkdir()
            sample.write_text(
                "src,dst,time\n"
                + "".join(f"node-{idx % 5},node-{(idx + 1) % 5},{idx}.5\n" for idx in range(16)),
                encoding="utf-8",
            )
            sample_hash = sha256(sample)
            (sample.parent / "metadata.json").write_text(
                json.dumps(
                    {
                        "input_kind": "real_dataset_prefix",
                        "source_url": "https://example.invalid/edges.csv",
                        "sample_sha256": sample_hash,
                    }
                ),
                encoding="utf-8",
            )
            output = root / "fixture"
            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/generate_u280_comparison_fixture.py"),
                    "--dataset",
                    "WK",
                    "--model",
                    "TGAT",
                    "--batch-size",
                    "8",
                    "--input",
                    str(sample),
                    "--output",
                    str(output),
                ],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            )
            metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["input_kind"], "real_dataset_prefix")
            self.assertEqual(metadata["input_sha256"], sample_hash)
            self.assertEqual(metadata["num_vertices"], 5)
            self.assertEqual(metadata["fanout"], 20)
            self.assertEqual(metadata["depth"], 2)
            self.assertEqual(metadata["schema_version"], 4)
            self.assertEqual(
                metadata["timestamp_mapping"]["method"],
                "relative_source_time_quantized_by_median_positive_gap",
            )
            ticks = array("I")
            ticks.frombytes((output / "event_ts.bin").read_bytes())
            self.assertEqual(list(ticks), list(range(1, 17)))

    def test_kernel_scalar_arguments_separate_tempgnn_and_baselines(self) -> None:
        self.assertEqual(kernel_scalar_arguments("TempGNN", "TGAT", 2), (16, 1, 1))
        self.assertEqual(kernel_scalar_arguments("MATG", "TGAT", 2), (2, 2, 1))

    def test_machine_readable_host_output(self) -> None:
        values = parse_host_output(
            "\n".join(
                [
                    "kernel_time_ms=1.25",
                    "measurement_window_ms=1000",
                    "iterations=800",
                    "warmup_kernel_checksum=42",
                    "warmup_embedding_checksum=43",
                    "kernel_checksum=42",
                    "embedding_checksum=43",
                    "repeat_consistency=PASS",
                    "expected_kernel_checksum=42",
                    "expected_embedding_checksum=43",
                    "golden_validation=PASS",
                    "validation=PASS",
                    "stat[0]=8",
                ]
            )
        )
        self.assertEqual(values["validation"], "PASS")
        self.assertEqual(values["repeat_consistency"], "PASS")
        self.assertEqual(values["golden_validation"], "PASS")
        self.assertEqual(values["kernel_checksum"], "42")

    def test_xclbin_clock_parser_uses_link_request_not_shell_clocks(self) -> None:
        info = """
System Clocks
-------------
   Name:           ulp_ucs_aclk_kernel_00
   Type:           SCALABLE
   Default Freq:   300 MHz
   Requested Freq: 225 MHz
   Achieved Freq:  221.5 MHz
Command Line: v++ --freqhz 225000000:matg_kernel_1 --link
"""
        self.assertEqual(parse_xclbin_link_requested_frequency(info, "matg_kernel"), 225.0)

    def test_tempgnn_link_requests_the_configured_kernel_frequency(self) -> None:
        makefile = (REPO_ROOT / "hardware/vitis/Makefile").read_text(encoding="utf-8")
        self.assertIn("KERNEL_CLOCK_CUS ?= $(KERNEL_NAME)_1", makefile)
        self.assertIn("--freqhz $(FREQ_HZ):$(KERNEL_CLOCK_CUS)", makefile)

        root_makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("tempgnn_forward_u280_21cu.cfg", root_makefile)
        self.assertIn("U280_FORWARD_FREQ_HZ ?= 168000000", root_makefile)
        self.assertIn("KERNEL_CLOCK_CUS=\"$(U280_FORWARD_CLOCK_CUS)\"", root_makefile)
        self.assertNotIn("VPP_LINK_FLAGS ?= --freqhz", root_makefile)

    def test_tempgnn_parallel_layouts_bind_complete_compute_units(self) -> None:
        expected_ports = {
            "event_src",
            "event_dst",
            "event_ts",
            "vertex_offsets",
            "history_event_idx",
            "history_peer",
            "target_vertex",
            "target_event_idx",
            "initial_memory",
            "event_features",
            "weight_self",
            "weight_peer",
            "weight_event",
            "bias",
            "embedding_out",
            "stats_out",
        }

        for cu_count in (4, 12, 21):
            config = (
                REPO_ROOT / f"hardware/vitis/tempgnn_forward_u280_{cu_count}cu.cfg"
            ).read_text(encoding="utf-8")
            cu_names = ".".join(
                f"tempgnn_forward_kernel_{cu}" for cu in range(1, cu_count + 1)
            )
            self.assertIn(f"nk=tempgnn_forward_kernel:{cu_count}:{cu_names}", config)
            bindings = [line for line in config.splitlines() if line.startswith("sp=")]
            self.assertEqual(len(bindings), cu_count * len(expected_ports))
            for cu in range(1, cu_count + 1):
                prefix = f"sp=tempgnn_forward_kernel_{cu}."
                cu_bindings = [line for line in bindings if line.startswith(prefix)]
                port_to_bank = {
                    line.split(".", 1)[1].split(":", 1)[0]: int(
                        line.rsplit("[", 1)[1][:-1]
                    )
                    for line in cu_bindings
                }
                self.assertEqual(set(port_to_bank), expected_ports)
                bank_base = (
                    (cu - 1) * 2
                    if cu_count in (4, 12)
                    else [0, 1, 18, 19, 20, 21, 22, 2, 3, 4, 5, 6, 7, 8,
                          10, 11, 12, 13, 14, 15, 16][cu - 1]
                )
                self.assertEqual(
                    {port_to_bank[port] for port in expected_ports},
                    {bank_base},
                )
            if cu_count == 21:
                for cu in range(1, cu_count + 1):
                    expected_slr = (cu - 1) // 7
                    self.assertIn(
                        f"slr=tempgnn_forward_kernel_{cu}:SLR{expected_slr}",
                        config,
                    )

        kernel = (REPO_ROOT / "hardware/src/tempgnn_forward_kernel.cpp").read_text(
            encoding="utf-8"
        )
        bundles = {
            line.split("bundle=", 1)[1].split()[0]
            for line in kernel.splitlines()
            if "INTERFACE m_axi" in line
        }
        self.assertEqual(bundles, {"gmem0"})

        host = (REPO_ROOT / "hardware/host/tempgnn_forward_parallel_xrt_host.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("TEMPGNN_FORWARD_MAX_CUS = 32", host)
        self.assertIn(
            "for (uint32_t chunk = index; chunk < chunks; chunk += active_cus)",
            host,
        )
        self.assertIn("std::unique_ptr<xrt::run> run", host)
        self.assertIn("worker.run->start()", host)
        self.assertIn("fixture exceeds compiled forward-kernel capacity", host)
        self.assertIn("per-CU target partition exceeds compiled kernel capacity", host)

    def test_vivado_kernel_clock_parser(self) -> None:
        log = (
            "Connected </matg_kernel_1/ap_clk> with requested frequency of "
            "225.000000 MHz and tolerance of 11.250000 MHz to clock source "
            "</clk_wiz/clk_out1> with frequency of 225.000000 MHz."
        )
        self.assertEqual(parse_vivado_kernel_clock(log, "matg_kernel"), (225.0, 225.0))

    def test_post_route_timing_parser(self) -> None:
        report = """
| Design Timing Summary
| ---------------------
    WNS(ns)      TNS(ns)  TNS Failing Endpoints
    -------      -------  ---------------------
      0.016        0.000                      0
"""
        self.assertEqual(parse_post_route_timing(report), (0.016, 0.0))

    def test_evidence_command_redacts_repository_path(self) -> None:
        command = [str(REPO_ROOT / "artifacts/u280/bin/host"), "--device", "0"]
        portable = portable_command(command)
        self.assertTrue(portable[0].startswith("{repo}"))
        self.assertNotIn(str(REPO_ROOT), " ".join(portable))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
