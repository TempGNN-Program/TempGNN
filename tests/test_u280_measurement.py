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
