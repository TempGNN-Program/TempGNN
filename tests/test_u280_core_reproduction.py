from __future__ import annotations

import csv
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from scripts.run_u280_core_reproduction import (
    aggregate_measurements,
    compare_figure_csv,
    portable_command,
    preflight,
    resolve_source_commit,
    validate_frequency_comparability,
    validate_measurements,
)


class U280CoreReproductionTests(unittest.TestCase):
    def test_reviewer_contract_points_to_existing_config(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        contract = (repo_root / "artifacts/u280/README.md").read_text(encoding="utf-8")
        config = "configs/u280_core_reproduction.json"
        self.assertIn(config, contract)
        self.assertTrue((repo_root / config).is_file())

    def test_preflight_rejects_duplicate_xclbin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            systems = []
            shared_xclbin = root / "shared.xclbin"
            shared_xclbin.write_bytes(b"same kernel")
            for index, name in enumerate(("TempGNN", "MATG", "ViTeGNN", "RTGA")):
                runner = root / f"runner-{index}.sh"
                host = root / f"host-{index}"
                source = root / f"source-{index}.cpp"
                runner.write_text("#!/bin/sh\n", encoding="utf-8")
                host.write_bytes(f"host-{index}".encode())
                source.write_text(f"// source {index}\n", encoding="utf-8")
                systems.append(
                    {
                        "name": name,
                        "source_revision": f"revision-{index}",
                        "sources": [source.name],
                        "runner": runner.name,
                        "host": host.name,
                        "xclbin": shared_xclbin.name,
                        "command": [runner.name, name],
                    }
                )
            config = {"datasets": ["WK"], "models": ["TGN"], "systems": systems}
            with self.assertRaises(SystemExit) as context:
                preflight(config, root)
            self.assertIn("byte-identical", str(context.exception))

    def test_validate_and_aggregate_repeated_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw = root / "measurements.csv"
            fields = [
                "dataset",
                "model",
                "solution",
                "repetition",
                "batch_size",
                "latency_ms",
                "power_w",
                "energy_mj",
                "frequency_mhz",
                "requested_frequency_mhz",
                "xclbin_link_requested_frequency_mhz",
                "post_route_kernel_frequency_mhz",
                "post_route_wns_ns",
                "post_route_tns_ns",
                "timing_met",
                "fixture_input_kind",
                "fixture_input_sha256",
                "fixture_source_url",
                "golden_validation",
                "repeat_consistency",
                "golden_embedding_sha256",
                "golden_stats_sha256",
                "power_samples",
                "power_min_w",
                "power_max_w",
                "kernel_iterations",
                "kernel_checksum",
                "embedding_checksum",
                "warmup_kernel_checksum",
                "warmup_embedding_checksum",
                "expected_kernel_checksum",
                "expected_embedding_checksum",
                "xclbin_sha256",
                "host_sha256",
                "fixture_metadata_sha256",
                "measurement_utc",
            ]
            rows = []
            for repetition, latency in ((1, 2.0), (2, 4.0)):
                rows.append(
                    {
                        "dataset": "WK",
                        "model": "TGN",
                        "solution": "TempGNN",
                        "repetition": repetition,
                        "batch_size": 1000,
                        "latency_ms": latency,
                        "power_w": 2.0,
                        "energy_mj": latency * 2.0,
                        "frequency_mhz": 225,
                        "requested_frequency_mhz": 225,
                        "xclbin_link_requested_frequency_mhz": 225,
                        "post_route_kernel_frequency_mhz": 225,
                        "post_route_wns_ns": 0.016,
                        "post_route_tns_ns": 0.0,
                        "timing_met": "PASS",
                        "fixture_input_kind": "real_dataset_prefix",
                        "fixture_input_sha256": "a" * 64,
                        "fixture_source_url": "https://example.invalid/edges.csv",
                        "golden_validation": "PASS",
                        "repeat_consistency": "PASS",
                        "golden_embedding_sha256": "b" * 64,
                        "golden_stats_sha256": "c" * 64,
                        "power_samples": 4,
                        "power_min_w": 1.9,
                        "power_max_w": 2.1,
                        "kernel_iterations": 10,
                        "kernel_checksum": "101",
                        "embedding_checksum": "202",
                        "warmup_kernel_checksum": "101",
                        "warmup_embedding_checksum": "202",
                        "expected_kernel_checksum": "101",
                        "expected_embedding_checksum": "202",
                        "xclbin_sha256": "d" * 64,
                        "host_sha256": "e" * 64,
                        "fixture_metadata_sha256": "f" * 64,
                        "measurement_utc": "2026-07-15T00:00:00+00:00",
                    }
                )
            with raw.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            validated = validate_measurements(
                raw,
                name="TempGNN",
                datasets=("WK",),
                models=("TGN",),
                repetitions=2,
                energy_tolerance=0.01,
            )
            aggregate = root / "aggregate.csv"
            aggregate_measurements(validated, aggregate)
            with aggregate.open(newline="", encoding="utf-8") as handle:
                result = next(csv.DictReader(handle))
            self.assertEqual(result["repetitions"], "2")
            self.assertEqual(float(result["latency_ms"]), 3.0)
            self.assertEqual(float(result["energy_mj"]), 6.0)

            rows[1]["repetition"] = 1
            with raw.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(SystemExit, "duplicate repetition"):
                validate_measurements(
                    raw,
                    name="TempGNN",
                    datasets=("WK",),
                    models=("TGN",),
                    repetitions=2,
                    energy_tolerance=0.01,
                )

            rows[1]["repetition"] = 2
            with raw.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(SystemExit, "different xclbin"):
                validate_measurements(
                    raw,
                    name="TempGNN",
                    datasets=("WK",),
                    models=("TGN",),
                    repetitions=2,
                    energy_tolerance=0.01,
                    expected_xclbin_sha256="0" * 64,
                )

    def test_frequency_comparability_rejects_per_system_auto_scaling(self) -> None:
        rows = [
            {"solution": "TempGNN", "post_route_kernel_frequency_mhz": "225"},
            {"solution": "MATG", "post_route_kernel_frequency_mhz": "210"},
        ]
        with self.assertRaises(SystemExit):
            validate_frequency_comparability(rows, tolerance_mhz=0.5)

    def test_compare_can_limit_expected_solutions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = root / "expected.csv"
            actual = root / "actual.csv"
            fields = ["dataset", "figure", "model", "solution", "value"]
            expected_rows = [
                {"dataset": "WK", "figure": "fig12", "model": "TGN", "solution": "TempGNN", "value": 1.0},
                {"dataset": "WK", "figure": "fig12", "model": "TGN", "solution": "Cascade", "value": 3.0},
            ]
            actual_rows = [expected_rows[0]]
            for path, rows in ((expected, expected_rows), (actual, actual_rows)):
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            result = compare_figure_csv(expected, actual, 0.01, solutions={"TempGNN"})
            self.assertTrue(result["pass"])

    def test_provenance_command_redacts_repository_path(self) -> None:
        root = Path.home() / "anonymous-build" / "TempGNN"
        command = [str(root / "runner.sh"), str(root / "results.csv")]
        portable = portable_command(command, root)
        self.assertTrue(all(value.startswith("{repo}") for value in portable))
        self.assertNotIn(str(root), " ".join(portable))

    def test_source_commit_can_be_bound_for_non_git_measurement_stage(self) -> None:
        commit = "A" * 40
        with mock.patch.dict("os.environ", {"TEMPGNN_AE_SOURCE_COMMIT": commit}):
            resolved, source = resolve_source_commit(Path("/not/a/git/worktree"))
        self.assertEqual(resolved, commit.lower())
        self.assertEqual(source, "TEMPGNN_AE_SOURCE_COMMIT")

    def test_source_commit_binding_rejects_abbreviated_sha(self) -> None:
        with mock.patch.dict("os.environ", {"TEMPGNN_AE_SOURCE_COMMIT": "abc123"}):
            with self.assertRaisesRegex(SystemExit, "complete 40-character Git SHA"):
                resolve_source_commit(Path("/not/a/git/worktree"))


if __name__ == "__main__":
    unittest.main()
