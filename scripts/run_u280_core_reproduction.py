#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.derive_comparison_figures import U280_CORE_SOLUTIONS, derive_u280_core


REQUIRED_SYSTEMS = ("TempGNN", "MATG", "ViTeGNN", "RTGA")
REQUIRED_COLUMNS = {
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
}
PLACEHOLDERS = {"", "TODO", "TO_BE_FILLED", "UNKNOWN"}


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    config = load_config(args.config)
    artifact_records = preflight(config, repo_root)
    artifact_records_by_name = {str(record["name"]): record for record in artifact_records}

    if args.preflight_only:
        print_preflight(artifact_records)
        return

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.out / run_id
    if run_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing reviewer run: {run_dir}")
    run_dir.mkdir(parents=True)

    repetitions = args.repetitions or int(config.get("repetitions", 3))
    datasets = tuple(config["datasets"])
    models = tuple(config["models"])
    run_records = []
    all_measurement_rows: list[dict[str, str]] = []

    for system in config["systems"]:
        name = str(system["name"])
        raw_csv = run_dir / "raw" / name / "measurements.csv"
        raw_csv.parent.mkdir(parents=True)
        log_path = raw_csv.with_suffix(".log")
        command = render_command(
            system,
            repo_root=repo_root,
            raw_csv=raw_csv,
            device=args.device,
            repetitions=repetitions,
            datasets=datasets,
            models=models,
        )
        env = os.environ.copy()
        env.update(
            {
                "TEMPGNN_AE_RUN_ID": run_id,
                "TEMPGNN_AE_SYSTEM": name,
                "TEMPGNN_AE_RAW_CSV": str(raw_csv),
            }
        )
        with log_path.open("w", encoding="utf-8") as log_handle:
            subprocess.run(
                command,
                cwd=repo_root,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                check=True,
            )

        artifact_hashes = artifact_records_by_name[name]["sha256"]
        assert isinstance(artifact_hashes, dict)
        rows = validate_measurements(
            raw_csv,
            name=name,
            datasets=datasets,
            models=models,
            repetitions=repetitions,
            energy_tolerance=float(config.get("energy_consistency_tolerance", 0.05)),
            requested_frequency_mhz=float(config.get("requested_frequency_mhz", 225)),
            frequency_tolerance_mhz=float(
                config.get("frequency_comparison_tolerance_mhz", 0.5)
            ),
            expected_xclbin_sha256=str(artifact_hashes["xclbin"]),
            expected_host_sha256=str(artifact_hashes["host"]),
            fixture_root=repo_root / "results/generated_u280_comparison_fixtures",
        )
        all_measurement_rows.extend(rows)
        aggregate_path = aggregate_destination(run_dir, name)
        aggregate_path.parent.mkdir(parents=True, exist_ok=True)
        aggregate_measurements(rows, aggregate_path)
        run_records.append(
            {
                "name": name,
                "command": portable_command(command, repo_root),
                "raw_csv": relative_to(raw_csv, run_dir),
                "log": relative_to(log_path, run_dir),
                "aggregate_csv": relative_to(aggregate_path, run_dir),
            }
        )

    validate_frequency_comparability(
        all_measurement_rows,
        tolerance_mhz=float(config.get("frequency_comparison_tolerance_mhz", 0.5)),
    )

    derived_dir = run_dir / "derived_comparison_figures"
    derive_u280_core(run_dir / "baselines_u280", derived_dir)
    checks = verify_core_figures(
        args.reference_dir,
        derived_dir,
        speedup_threshold=args.speedup_threshold,
        energy_threshold=args.energy_threshold,
    )
    write_verification(run_dir, checks)
    write_provenance(
        run_dir,
        config=config,
        artifact_records=artifact_records,
        run_records=run_records,
        run_id=run_id,
        device=args.device,
        repetitions=repetitions,
        repo_root=repo_root,
    )

    failed = [name for name, result in checks.items() if not result["pass"]]
    if failed:
        message = f"U280 comparison did not meet paper-figure tolerances: {', '.join(failed)}"
        if bool(config.get("results_reproduced_eligible", False)) or args.require_paper_match:
            raise SystemExit(message)
        print(f"{message} (diagnostic status recorded; run completed)")
        return
    if bool(config.get("results_reproduced_eligible", False)):
        print(f"U280 paper-equivalent reproduction PASS: {run_id}")
    else:
        print(f"U280 diagnostic comparison PASS (not paper-equivalent): {run_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run four distinct U280 implementations and regenerate core Fig.11/Fig.12 data."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/u280_core_reproduction.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("results/reviewer_u280_runs"),
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=Path("results/paper_reproduction"),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--device", default="0")
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--speedup-threshold", type=float, default=0.05)
    parser.add_argument("--energy-threshold", type=float, default=0.10)
    parser.add_argument(
        "--require-paper-match",
        action="store_true",
        help="return failure when the regenerated core figures exceed the configured tolerances",
    )
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def load_config(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise SystemExit(
            f"Missing U280 core config: {path}. Start from "
            "configs/u280_core_reproduction.example.json and point it at the four real implementations."
        )
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise SystemExit("U280 core config must be a JSON object")
    return config


def preflight(config: dict[str, object], repo_root: Path) -> list[dict[str, object]]:
    systems = config.get("systems")
    if not isinstance(systems, list):
        raise SystemExit("Config field 'systems' must be a list")
    names = [str(system.get("name", "")) for system in systems if isinstance(system, dict)]
    if set(names) != set(REQUIRED_SYSTEMS) or len(names) != len(REQUIRED_SYSTEMS):
        raise SystemExit(
            "Config must contain exactly four systems: " + ", ".join(REQUIRED_SYSTEMS)
        )
    for key in ("datasets", "models"):
        values = config.get(key)
        if not isinstance(values, list) or not values:
            raise SystemExit(f"Config field '{key}' must be a non-empty list")

    records = []
    xclbin_hashes: dict[str, str] = {}
    rendered_commands = set()
    for system in systems:
        assert isinstance(system, dict)
        name = str(system["name"])
        revision = str(system.get("source_revision", ""))
        if revision in PLACEHOLDERS:
            raise SystemExit(f"{name}: source_revision must identify the reproduced implementation")
        command = system.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            raise SystemExit(f"{name}: command must be a non-empty JSON string array")
        command_key = json.dumps(command, sort_keys=True)
        if command_key in rendered_commands:
            raise SystemExit(f"{name}: command duplicates another implementation")
        rendered_commands.add(command_key)

        paths = {}
        hashes = {}
        for key in ("runner", "host", "xclbin"):
            value = str(system.get(key, ""))
            if value in PLACEHOLDERS:
                raise SystemExit(f"{name}: missing {key} path")
            resolved = resolve_repo_path(repo_root, value)
            if not resolved.is_file():
                raise SystemExit(f"{name}: required {key} does not exist: {resolved}")
            paths[key] = resolved
            hashes[key] = sha256_file(resolved)

        source_values = system.get("sources")
        if not isinstance(source_values, list) or not source_values or not all(
            isinstance(value, str) for value in source_values
        ):
            raise SystemExit(f"{name}: sources must be a non-empty JSON string array")
        source_paths = []
        source_hashes = {}
        for value in source_values:
            resolved = resolve_repo_path(repo_root, value)
            if not resolved.is_file():
                raise SystemExit(f"{name}: required source does not exist: {resolved}")
            relative = str(resolved.relative_to(repo_root))
            source_paths.append(relative)
            source_hashes[relative] = sha256_file(resolved)
        paths["sources"] = source_paths
        hashes["sources"] = source_hashes

        build_source_values = system.get("build_sources", source_values)
        if not isinstance(build_source_values, list) or not build_source_values or not all(
            isinstance(value, str) for value in build_source_values
        ):
            raise SystemExit(f"{name}: build_sources must be a non-empty JSON string array")
        build_source_paths = []
        build_source_hashes = {}
        for value in build_source_values:
            resolved = resolve_repo_path(repo_root, value)
            if not resolved.is_file():
                raise SystemExit(f"{name}: required build source does not exist: {resolved}")
            relative = str(resolved.relative_to(repo_root))
            build_source_paths.append(relative)
            build_source_hashes[relative] = sha256_file(resolved)
        paths["build_sources"] = build_source_paths
        hashes["build_sources"] = build_source_hashes

        xclbin_hash = hashes["xclbin"]
        duplicate = xclbin_hashes.get(xclbin_hash)
        if duplicate:
            raise SystemExit(
                f"{name}: xclbin is byte-identical to {duplicate}; each baseline must use its own implementation"
            )
        xclbin_hashes[xclbin_hash] = name
        records.append(
            {
                "name": name,
                "source_revision": revision,
                "paths": {
                    key: (
                        value
                        if isinstance(value, list)
                        else str(value.relative_to(repo_root))
                    )
                    for key, value in paths.items()
                },
                "sha256": hashes,
            }
        )
    expected_frequency = float(config.get("requested_frequency_mhz", 225))
    frequency_tolerance = float(config.get("frequency_comparison_tolerance_mhz", 0.5))
    for record in records:
        paths = record["paths"]
        hashes = record["sha256"]
        assert isinstance(paths, dict) and isinstance(hashes, dict)
        xclbin_path = resolve_repo_path(repo_root, str(paths["xclbin"]))
        provenance_path = xclbin_path.parent.parent / "evidence" / "build_provenance.json"
        clock_evidence = validate_packaged_build_provenance(
            name=str(record["name"]),
            provenance_path=provenance_path,
            xclbin_sha256=str(hashes["xclbin"]),
            source_hashes=hashes["sources"],
            build_source_hashes=hashes["build_sources"],
            expected_frequency_mhz=expected_frequency,
            frequency_tolerance_mhz=frequency_tolerance,
        )
        record["clock_evidence"] = clock_evidence
    return records


def validate_packaged_build_provenance(
    *,
    name: str,
    provenance_path: Path,
    xclbin_sha256: str,
    source_hashes: object,
    build_source_hashes: object,
    expected_frequency_mhz: float,
    frequency_tolerance_mhz: float,
) -> dict[str, object]:
    if not provenance_path.is_file():
        raise SystemExit(f"{name}: missing packaged build provenance: {provenance_path}")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get("system") != name:
        raise SystemExit(f"{name}: packaged build provenance names another system")
    if provenance.get("distributed_xclbin_sha256") != xclbin_sha256:
        raise SystemExit(f"{name}: packaged xclbin hash disagrees with build provenance")
    if not isinstance(source_hashes, dict):
        raise SystemExit(f"{name}: internal source-hash record is invalid")
    normalized_sources = {Path(key).as_posix(): value for key, value in source_hashes.items()}
    if provenance.get("source_files_sha256") != normalized_sources:
        raise SystemExit(f"{name}: current source hashes disagree with build provenance")
    if not isinstance(build_source_hashes, dict):
        raise SystemExit(f"{name}: internal build-source hash record is invalid")
    normalized_build_sources = {
        Path(key).as_posix(): value for key, value in build_source_hashes.items()
    }
    if provenance.get("build_input_files_sha256") != normalized_build_sources:
        raise SystemExit(f"{name}: current build-input hashes disagree with build provenance")
    link_frequency = float(provenance["xclbin_link_requested_frequency_mhz"])
    post_route_frequency = float(provenance["post_route_kernel_frequency_mhz"])
    post_route_wns = float(provenance["post_route_wns_ns"])
    post_route_tns = float(provenance["post_route_tns_ns"])
    for label, value in (
        ("xclbin link request", link_frequency),
        ("post-route kernel clock", post_route_frequency),
    ):
        if abs(value - expected_frequency_mhz) > frequency_tolerance_mhz:
            raise SystemExit(
                f"{name}: {label} is {value:.3f} MHz, expected "
                f"{expected_frequency_mhz:.3f} MHz"
            )
    if provenance.get("post_route_timing_met") is not True or post_route_wns < 0 or post_route_tns < 0:
        raise SystemExit(f"{name}: packaged post-route timing evidence does not pass")
    return {
        "xclbin_link_requested_frequency_mhz": link_frequency,
        "post_route_kernel_frequency_mhz": post_route_frequency,
        "post_route_wns_ns": post_route_wns,
        "post_route_tns_ns": post_route_tns,
        "timing_met": True,
    }


def render_command(
    system: dict[str, object],
    *,
    repo_root: Path,
    raw_csv: Path,
    device: str,
    repetitions: int,
    datasets: tuple[str, ...],
    models: tuple[str, ...],
) -> list[str]:
    replacements = {
        "repo": str(repo_root),
        "runner": str(resolve_repo_path(repo_root, str(system["runner"]))),
        "host": str(resolve_repo_path(repo_root, str(system["host"]))),
        "xclbin": str(resolve_repo_path(repo_root, str(system["xclbin"]))),
        "raw_csv": str(raw_csv.resolve()),
        "device": str(device),
        "repetitions": str(repetitions),
        "datasets": ",".join(datasets),
        "models": ",".join(models),
    }
    return [str(part).format(**replacements) for part in system["command"]]


def validate_measurements(
    path: Path,
    *,
    name: str,
    datasets: tuple[str, ...],
    models: tuple[str, ...],
    repetitions: int,
    energy_tolerance: float,
    requested_frequency_mhz: float | None = None,
    frequency_tolerance_mhz: float = 0.5,
    expected_xclbin_sha256: str | None = None,
    expected_host_sha256: str | None = None,
    fixture_root: Path | None = None,
) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"{name}: runner did not create {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - fields)
        if missing:
            raise SystemExit(f"{name}: raw CSV is missing columns: {', '.join(missing)}")
        rows = list(reader)

    expected_keys = {(dataset, model) for dataset in datasets for model in models}
    counts: dict[tuple[str, str], int] = defaultdict(int)
    seen_repetitions: dict[tuple[str, str], set[int]] = defaultdict(set)
    for row in rows:
        if row["solution"] != name:
            raise SystemExit(f"{name}: found mismatched solution {row['solution']!r}")
        key = (row["dataset"], row["model"])
        if key not in expected_keys:
            raise SystemExit(f"{name}: unexpected dataset/model row: {key}")
        counts[key] += 1
        latency = positive_float(row, "latency_ms", name)
        power = positive_float(row, "power_w", name)
        energy = positive_float(row, "energy_mj", name)
        post_route_frequency = positive_float(row, "frequency_mhz", name)
        recorded_request = positive_float(row, "requested_frequency_mhz", name)
        xclbin_request = positive_float(row, "xclbin_link_requested_frequency_mhz", name)
        recorded_post_route = positive_float(row, "post_route_kernel_frequency_mhz", name)
        if abs(post_route_frequency - recorded_post_route) > 1e-6:
            raise SystemExit(f"{name}: frequency_mhz does not match post-route kernel frequency")
        try:
            post_route_wns = float(row["post_route_wns_ns"])
            post_route_tns = float(row["post_route_tns_ns"])
        except ValueError as exc:
            raise SystemExit(f"{name}: post-route WNS/TNS must be numeric") from exc
        if row["timing_met"] != "PASS" or post_route_wns < 0 or post_route_tns < 0:
            raise SystemExit(f"{name}: post-route timing evidence does not pass")
        if requested_frequency_mhz is not None:
            if abs(recorded_request - requested_frequency_mhz) > frequency_tolerance_mhz:
                raise SystemExit(f"{name}: runner requested frequency differs from the configuration")
            if abs(xclbin_request - requested_frequency_mhz) > frequency_tolerance_mhz:
                raise SystemExit(
                    f"{name}: xclbin link requested {xclbin_request:.3f} MHz, expected "
                    f"{requested_frequency_mhz:.3f} MHz"
                )
            if abs(recorded_post_route - requested_frequency_mhz) > frequency_tolerance_mhz:
                raise SystemExit(
                    f"{name}: post-route kernel clock is {recorded_post_route:.3f} MHz, expected "
                    f"{requested_frequency_mhz:.3f} MHz"
                )
        positive_float(row, "batch_size", name)
        if row["fixture_input_kind"] != "real_dataset_prefix":
            raise SystemExit(
                f"{name}: core comparison requires real_dataset_prefix inputs, found "
                f"{row['fixture_input_kind']!r}"
            )
        if len(row["fixture_input_sha256"]) != 64 or not row["fixture_source_url"].startswith(
            "https://"
        ):
            raise SystemExit(f"{name}: real-dataset provenance is incomplete for {key}")
        for field in (
            "fixture_input_sha256",
            "fixture_metadata_sha256",
            "golden_embedding_sha256",
            "golden_stats_sha256",
            "xclbin_sha256",
            "host_sha256",
        ):
            if not is_sha256(row[field]):
                raise SystemExit(f"{name}: {field} is not a SHA256 digest for {key}")
        if expected_xclbin_sha256 is not None and row["xclbin_sha256"] != expected_xclbin_sha256:
            raise SystemExit(f"{name}: measurement row names a different xclbin for {key}")
        if expected_host_sha256 is not None and row["host_sha256"] != expected_host_sha256:
            raise SystemExit(f"{name}: measurement row names a different host binary for {key}")
        if fixture_root is not None:
            fixture_metadata = fixture_root / row["dataset"] / row["model"] / "metadata.json"
            if not fixture_metadata.is_file() or sha256_file(fixture_metadata) != row[
                "fixture_metadata_sha256"
            ]:
                raise SystemExit(f"{name}: fixture metadata hash mismatch for {key}")
        if row["golden_validation"] != "PASS" or row["repeat_consistency"] != "PASS":
            raise SystemExit(f"{name}: checksum validation failed for {key}")
        checksum_fields = (
            "kernel_checksum",
            "embedding_checksum",
            "warmup_kernel_checksum",
            "warmup_embedding_checksum",
            "expected_kernel_checksum",
            "expected_embedding_checksum",
        )
        checksums = {field: positive_int(row, field, name) for field in checksum_fields}
        if not (
            checksums["kernel_checksum"]
            == checksums["warmup_kernel_checksum"]
            == checksums["expected_kernel_checksum"]
            and checksums["embedding_checksum"]
            == checksums["warmup_embedding_checksum"]
            == checksums["expected_embedding_checksum"]
        ):
            raise SystemExit(f"{name}: checksum columns disagree for {key}")
        power_samples = positive_int(row, "power_samples", name)
        kernel_iterations = positive_int(row, "kernel_iterations", name)
        power_min = positive_float(row, "power_min_w", name)
        power_max = positive_float(row, "power_max_w", name)
        if power_min > power or power > power_max or power_min > power_max:
            raise SystemExit(f"{name}: power summary is inconsistent for {key}")
        if power_samples < 1 or kernel_iterations < 1:
            raise SystemExit(f"{name}: measurement counters are invalid for {key}")
        try:
            measured_at = datetime.fromisoformat(row["measurement_utc"])
        except ValueError as exc:
            raise SystemExit(f"{name}: measurement_utc is not ISO-8601 for {key}") from exc
        if measured_at.tzinfo is None:
            raise SystemExit(f"{name}: measurement_utc must include a timezone for {key}")
        try:
            repetition = int(row["repetition"])
        except ValueError as exc:
            raise SystemExit(f"{name}: repetition must be an integer") from exc
        if not 1 <= repetition <= repetitions:
            raise SystemExit(f"{name}: repetition {repetition} is outside 1..{repetitions}")
        if repetition in seen_repetitions[key]:
            raise SystemExit(f"{name}: duplicate repetition {repetition} for {key}")
        seen_repetitions[key].add(repetition)
        calculated = latency * power
        relative_error = abs(energy - calculated) / energy
        if relative_error > energy_tolerance:
            raise SystemExit(
                f"{name}: energy_mj is inconsistent with latency_ms * power_w "
                f"({relative_error:.2%} > {energy_tolerance:.2%})"
            )

    missing_keys = sorted(expected_keys - set(counts))
    if missing_keys:
        raise SystemExit(f"{name}: missing dataset/model measurements: {missing_keys}")
    wrong_counts = {key: count for key, count in counts.items() if count != repetitions}
    if wrong_counts:
        raise SystemExit(f"{name}: expected {repetitions} repetitions per dataset/model: {wrong_counts}")
    return rows


def validate_frequency_comparability(
    rows: Iterable[dict[str, str]], *, tolerance_mhz: float
) -> None:
    by_solution: dict[str, set[float]] = defaultdict(set)
    for row in rows:
        by_solution[row["solution"]].add(float(row["post_route_kernel_frequency_mhz"]))
    inconsistent = {name: values for name, values in by_solution.items() if len(values) != 1}
    if inconsistent:
        raise SystemExit(f"post-route frequency changed within an implementation: {inconsistent}")
    implemented = {name: next(iter(values)) for name, values in by_solution.items()}
    if implemented and max(implemented.values()) - min(implemented.values()) > tolerance_mhz:
        raise SystemExit(
            "the four implementations do not have comparable post-route clocks: "
            + ", ".join(
                f"{name}={value:.3f} MHz" for name, value in sorted(implemented.items())
            )
        )


def aggregate_measurements(rows: Iterable[dict[str, str]], path: Path) -> None:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["dataset"], row["model"], row["solution"])].append(row)

    output = []
    for (dataset, model, solution), group in sorted(grouped.items()):
        latencies = [float(row["latency_ms"]) for row in group]
        powers = [float(row["power_w"]) for row in group]
        energies = [float(row["energy_mj"]) for row in group]
        frequencies = [float(row["frequency_mhz"]) for row in group]
        requested_frequencies = [float(row["requested_frequency_mhz"]) for row in group]
        xclbin_link_requested_frequencies = [
            float(row["xclbin_link_requested_frequency_mhz"]) for row in group
        ]
        post_route_wns = [float(row["post_route_wns_ns"]) for row in group]
        post_route_tns = [float(row["post_route_tns_ns"]) for row in group]
        batch_sizes = {int(row["batch_size"]) for row in group}
        if len(batch_sizes) != 1:
            raise SystemExit(f"{solution}: inconsistent batch sizes for {dataset}/{model}")
        output.append(
            {
                "dataset": dataset,
                "model": model,
                "solution": solution,
                "batch_size": batch_sizes.pop(),
                "latency_ms": rounded_mean(latencies),
                "power_w": rounded_mean(powers),
                "energy_mj": rounded_mean(energies),
                "frequency_mhz": rounded_mean(frequencies),
                "requested_frequency_mhz": rounded_mean(requested_frequencies),
                "xclbin_link_requested_frequency_mhz": rounded_mean(
                    xclbin_link_requested_frequencies
                ),
                "post_route_kernel_frequency_mhz": rounded_mean(frequencies),
                "post_route_wns_ns": rounded_mean(post_route_wns),
                "post_route_tns_ns": rounded_mean(post_route_tns),
                "timing_met": "PASS",
                "repetitions": len(group),
                "latency_stddev_ms": rounded_stdev(latencies),
                "power_stddev_w": rounded_stdev(powers),
                "energy_stddev_mj": rounded_stdev(energies),
                "measurement_date": datetime.now(timezone.utc).date().isoformat(),
            }
        )

    fieldnames = list(output[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output)


def verify_core_figures(
    reference_dir: Path,
    derived_dir: Path,
    *,
    speedup_threshold: float,
    energy_threshold: float,
) -> dict[str, dict[str, object]]:
    return {
        "fig11_speedup_matg": compare_figure_csv(
            reference_dir / "fig11_speedup_matg.csv",
            derived_dir / "fig11_speedup_matg.csv",
            speedup_threshold,
        ),
        "fig12_energy_tempgnn": compare_figure_csv(
            reference_dir / "fig12_energy_tempgnn.csv",
            derived_dir / "fig12_energy_tempgnn.csv",
            energy_threshold,
            solutions=set(U280_CORE_SOLUTIONS),
        ),
    }


def compare_figure_csv(
    expected_path: Path,
    actual_path: Path,
    threshold: float,
    solutions: set[str] | None = None,
) -> dict[str, object]:
    expected = index_figure(expected_path)
    actual = index_figure(actual_path)
    if solutions is not None:
        expected = {key: value for key, value in expected.items() if key[2] in solutions}
        actual = {key: value for key, value in actual.items() if key[2] in solutions}
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    max_error = 0.0
    worst_key = ""
    for key in sorted(set(expected) & set(actual)):
        denominator = abs(expected[key]) or 1.0
        error = abs(actual[key] - expected[key]) / denominator
        if error > max_error:
            max_error = error
            worst_key = "|".join(key)
    return {
        "pass": not missing and not extra and max_error <= threshold,
        "threshold": threshold,
        "max_relative_error": max_error,
        "worst_key": worst_key,
        "missing_keys": ["|".join(key) for key in missing],
        "extra_keys": ["|".join(key) for key in extra],
        "expected_csv": str(expected_path),
        "actual_csv": str(actual_path),
    }


def index_figure(path: Path) -> dict[tuple[str, str, str], float]:
    if not path.is_file():
        raise SystemExit(f"Missing figure CSV: {path}")
    values = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("model") == "AVG":
                continue
            values[(row["dataset"], row["model"], row["solution"])] = float(row["value"])
    return values


def write_verification(run_dir: Path, checks: dict[str, dict[str, object]]) -> None:
    (run_dir / "verification.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# U280 Comparison Verification",
        "",
        "| Figure | Max relative error | Threshold | Status |",
        "| --- | ---: | ---: | --- |",
    ]
    for name, result in checks.items():
        status = "PASS" if result["pass"] else "FAIL"
        lines.append(
            f"| {name} | {float(result['max_relative_error']):.6f} | "
            f"{float(result['threshold']):.6f} | {status} |"
        )
    lines.append("")
    (run_dir / "verification.md").write_text("\n".join(lines), encoding="utf-8")


def write_provenance(
    run_dir: Path,
    *,
    config: dict[str, object],
    artifact_records: list[dict[str, object]],
    run_records: list[dict[str, object]],
    run_id: str,
    device: str,
    repetitions: int,
    repo_root: Path,
) -> None:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = "unavailable"
    provenance = {
        "schema_version": 1,
        "paper_id": config.get("paper_id", "pap142"),
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "device": device,
        "repetitions": repetitions,
        "platform": config.get("platform"),
        "comparison_scope": config.get("comparison_scope"),
        "results_reproduced_eligible": bool(config.get("results_reproduced_eligible", False)),
        "methodology_differences": config.get("methodology_differences", []),
        "artifacts": artifact_records,
        "runs": run_records,
    }
    (run_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def aggregate_destination(run_dir: Path, name: str) -> Path:
    root = run_dir / "baselines_u280"
    if name == "TempGNN":
        return root / "raw_tempgnn_u280.csv"
    return root / name / "raw_latency_power_energy.csv"


def resolve_repo_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def relative_to(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def portable_command(command: list[str], repo_root: Path) -> list[str]:
    root = str(repo_root.resolve())
    home = str(Path.home())
    portable = []
    for argument in command:
        value = argument.replace(root, "{repo}")
        if home and home != root:
            value = value.replace(home, "{home}")
        portable.append(value)
    return portable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def positive_float(row: dict[str, str], field: str, name: str) -> float:
    try:
        value = float(row[field])
    except ValueError as exc:
        raise SystemExit(f"{name}: {field} must be numeric") from exc
    if value <= 0:
        raise SystemExit(f"{name}: {field} must be positive")
    return value


def positive_int(row: dict[str, str], field: str, name: str) -> int:
    try:
        value = int(row[field])
    except ValueError as exc:
        raise SystemExit(f"{name}: {field} must be an integer") from exc
    if value <= 0:
        raise SystemExit(f"{name}: {field} must be positive")
    return value


def is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value.lower())


def rounded_mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 8)


def rounded_stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return round(statistics.stdev(values), 8)


def print_preflight(records: list[dict[str, object]]) -> None:
    print("U280 four-implementation preflight PASS")
    for record in records:
        hashes = record["sha256"]
        clock = record["clock_evidence"]
        assert isinstance(hashes, dict)
        assert isinstance(clock, dict)
        print(
            f"{record['name']}: xclbin_sha256={hashes['xclbin']} "
            f"post_route_frequency_mhz={float(clock['post_route_kernel_frequency_mhz']):.3f} "
            f"WNS_ns={float(clock['post_route_wns_ns']):.3f} "
            f"TNS_ns={float(clock['post_route_tns_ns']):.3f}"
        )


if __name__ == "__main__":
    main()
