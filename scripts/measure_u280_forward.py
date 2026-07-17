#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


MODEL_IDS = {"JODIE": 0, "TGN": 1, "TGAT": 2, "APAN": 3}
DATASET_ALIASES = {"WK", "MC", "RT", "LM", "WT", "GT"}
POWER_PATTERN = re.compile(r"^\s*Power\s*:\s*([0-9.]+)\s+Watts", re.MULTILINE)
BDF_PATTERN = re.compile(r"\[([0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7])\]")
XCLBIN_LINK_FREQ_PATTERN = re.compile(
    r"--freqhz(?:=|\s+)(?P<hz>[0-9]+):(?P<instance>[A-Za-z0-9_.-]+)"
)
VIVADO_KERNEL_CLOCK_PATTERN = re.compile(
    r"Connected\s+</(?P<instance_path>[^>]+)/ap_clk>\s+"
    r"with requested frequency of\s+(?P<requested>[0-9.]+)\s+MHz.*?"
    r"clock source\s+</[^>]+>\s+with frequency of\s+"
    r"(?P<implemented>[0-9.]+)\s+MHz",
    re.DOTALL,
)
DESIGN_TIMING_PATTERN = re.compile(
    r"WNS\(ns\).*?TNS\(ns\).*?\n\s*-+.*?\n\s*"
    r"(?P<wns>[+-]?[0-9.]+)\s+(?P<tns>[+-]?[0-9.]+)",
    re.DOTALL,
)
REQUIRED_HOST_KEYS = {
    "kernel_time_ms",
    "measurement_window_ms",
    "kernel_checksum",
    "embedding_checksum",
    "warmup_kernel_checksum",
    "warmup_embedding_checksum",
    "repeat_consistency",
    "expected_kernel_checksum",
    "expected_embedding_checksum",
    "golden_validation",
    "validation",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure one forward-path implementation on U280 and emit raw AE rows."
    )
    parser.add_argument("--solution", required=True, choices=("TempGNN", "MATG", "ViTeGNN", "RTGA"))
    parser.add_argument("--kernel-name", required=True)
    parser.add_argument("--host", required=True, type=Path)
    parser.add_argument("--xclbin", required=True, type=Path)
    parser.add_argument("--device", default="0")
    parser.add_argument("--datasets", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--repetitions", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--fixture-root", type=Path, default=Path("results/generated_u280_comparison_fixtures")
    )
    parser.add_argument(
        "--dataset-sample-root", type=Path, default=Path("external/u280_dataset_samples")
    )
    parser.add_argument(
        "--synthetic-fixtures",
        action="store_true",
        help="Development-only mode; rows are marked synthetic_smoke and rejected by the core workflow",
    )
    parser.add_argument(
        "--baseline-reference",
        type=Path,
        help="C-sim reference executable required for MATG/ViTeGNN/RTGA",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--requested-frequency-mhz",
        "--frequency-mhz",
        dest="requested_frequency_mhz",
        type=float,
        default=225.0,
        help=(
            "requested kernel frequency; the emitted comparison clock is verified from "
            "packaged Vivado post-route provenance"
        ),
    )
    parser.add_argument(
        "--mode",
        type=int,
        default=1,
        help="baseline mode selector; the fresh comparison uses the bounded ViTeGNN bal-inspired path (1)",
    )
    parser.add_argument("--measurement-window-ms", type=float, default=3000.0)
    parser.add_argument("--max-iterations", type=int, default=10000)
    parser.add_argument("--power-interval-s", type=float, default=0.15)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.repetitions <= 0:
        raise SystemExit("repetitions must be positive")
    if not args.host.is_file() or not args.xclbin.is_file():
        raise SystemExit("host and xclbin must both exist")
    datasets = parse_csv_option(args.datasets, "datasets")
    unknown_datasets = sorted(set(datasets) - DATASET_ALIASES)
    if unknown_datasets:
        raise SystemExit(f"unsupported datasets: {', '.join(unknown_datasets)}")
    models = parse_csv_option(args.models, "models")
    unknown_models = sorted(set(models) - set(MODEL_IDS))
    if unknown_models:
        raise SystemExit(f"unsupported models: {', '.join(unknown_models)}")
    power_tool = shutil.which("xbutil")
    if not power_tool:
        raise SystemExit("xbutil is required for board power measurement")
    power_device = resolve_power_device(power_tool, args.device)
    clock_evidence = read_packaged_clock_evidence(
        args.xclbin,
        kernel_name=args.kernel_name,
        target_mhz=args.requested_frequency_mhz,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    log_root = args.output.parent / (args.output.stem + "_evidence")
    log_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    xclbin_sha = sha256_file(args.xclbin)
    host_sha = sha256_file(args.host)

    for dataset in datasets:
        for model in models:
            fixture = args.fixture_root / dataset / model
            generate_fixture(
                dataset,
                model,
                fixture,
                args.batch_size,
                sample_root=args.dataset_sample_root,
                synthetic=args.synthetic_fixtures,
            )
            metadata = json.loads((fixture / "metadata.json").read_text(encoding="utf-8"))
            fanout = int(metadata["fanout"])
            depth = int(metadata["depth"])
            prepare_golden(args, fixture, fanout=fanout, depth=depth, model=model)
            arg13, arg14, arg15 = kernel_scalar_arguments(args.solution, model, args.mode)
            calibration_command = host_command(
                args,
                fixture,
                fanout=fanout,
                depth=depth,
                arg13=arg13,
                arg14=arg14,
                arg15=arg15,
                warmup=1,
                iterations=1,
            )
            calibration = subprocess.run(
                calibration_command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=600,
            )
            calibration_values = parse_host_output(calibration.stdout)
            latency_hint = float(calibration_values["kernel_time_ms"])
            iterations = max(
                1,
                min(
                    args.max_iterations,
                    int(math.ceil(args.measurement_window_ms / max(latency_hint, 0.01))),
                ),
            )

            for repetition in range(1, args.repetitions + 1):
                command = host_command(
                    args,
                    fixture,
                    fanout=fanout,
                    depth=depth,
                    arg13=arg13,
                    arg14=arg14,
                    arg15=arg15,
                    warmup=1,
                    iterations=iterations,
                )
                evidence_prefix = log_root / f"{dataset}_{model}_r{repetition}"
                gate_prefix = evidence_prefix.with_name(evidence_prefix.name + "_gate")
                command.append(str(gate_prefix.resolve()))
                values, powers = run_with_power_sampling(
                    command,
                    gate_prefix=gate_prefix,
                    device=power_device,
                    power_tool=power_tool,
                    interval_s=args.power_interval_s,
                    timeout_s=max(900.0, args.measurement_window_ms / 1000.0 * 20.0),
                )
                if values["validation"] != "PASS":
                    raise SystemExit(f"{args.solution} validation failed for {dataset}/{model}")
                if values["repeat_consistency"] != "PASS":
                    raise SystemExit(
                        f"{args.solution} repeated output changed for {dataset}/{model}"
                    )
                if values["golden_validation"] != "PASS":
                    raise SystemExit(
                        f"{args.solution} hardware output differs from golden for {dataset}/{model}"
                    )
                if not powers:
                    raise SystemExit(f"no U280 power samples for {dataset}/{model}")
                latency_ms = float(values["kernel_time_ms"])
                power_w = statistics.fmean(powers)
                energy_mj = latency_ms * power_w
                row = {
                    "dataset": dataset,
                    "model": model,
                    "solution": args.solution,
                    "compute_units": values.get("compute_units", "1"),
                    "repetition": repetition,
                    "batch_size": args.batch_size,
                    "latency_ms": f"{latency_ms:.9f}",
                    "power_w": f"{power_w:.6f}",
                    "energy_mj": f"{energy_mj:.9f}",
                    # frequency_mhz remains the aggregation alias for the
                    # timing-closed post-route kernel clock.
                    "frequency_mhz": f"{clock_evidence['post_route_frequency_mhz']:.3f}",
                    "requested_frequency_mhz": f"{args.requested_frequency_mhz:.3f}",
                    "xclbin_link_requested_frequency_mhz": (
                        f"{clock_evidence['xclbin_link_requested_frequency_mhz']:.3f}"
                    ),
                    "post_route_kernel_frequency_mhz": (
                        f"{clock_evidence['post_route_frequency_mhz']:.3f}"
                    ),
                    "post_route_wns_ns": f"{clock_evidence['post_route_wns_ns']:.6f}",
                    "post_route_tns_ns": f"{clock_evidence['post_route_tns_ns']:.6f}",
                    "timing_met": "PASS",
                    "power_samples": len(powers),
                    "power_min_w": f"{min(powers):.6f}",
                    "power_max_w": f"{max(powers):.6f}",
                    "kernel_iterations": values["iterations"],
                    "kernel_checksum": values["kernel_checksum"],
                    "embedding_checksum": values["embedding_checksum"],
                    "warmup_kernel_checksum": values["warmup_kernel_checksum"],
                    "warmup_embedding_checksum": values["warmup_embedding_checksum"],
                    "repeat_consistency": values["repeat_consistency"],
                    "expected_kernel_checksum": values["expected_kernel_checksum"],
                    "expected_embedding_checksum": values["expected_embedding_checksum"],
                    "golden_validation": values["golden_validation"],
                    "golden_embedding_sha256": sha256_file(
                        fixture / f"expected_{args.kernel_name}_embedding.bin"
                    ),
                    "golden_stats_sha256": sha256_file(
                        fixture / f"expected_{args.kernel_name}_stats.bin"
                    ),
                    "xclbin_sha256": xclbin_sha,
                    "host_sha256": host_sha,
                    "fixture_metadata_sha256": sha256_file(fixture / "metadata.json"),
                    "fixture_input_kind": metadata["input_kind"],
                    "fixture_input_sha256": metadata["input_sha256"],
                    "fixture_source_url": metadata.get("input_source", {}).get("source_url", ""),
                    "measurement_utc": datetime.now(timezone.utc).isoformat(),
                }
                rows.append(row)
                write_evidence(
                    evidence_prefix,
                    command=command,
                    calibration_command=calibration_command,
                    host_values=values,
                    powers=powers,
                    row=row,
                )
                write_rows(args.output, rows)

    print(f"Wrote {len(rows)} raw U280 measurements")


def parse_csv_option(value: str, label: str) -> list[str]:
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    if not parsed:
        raise SystemExit(f"{label} cannot be empty")
    return parsed


def generate_fixture(
    dataset: str,
    model: str,
    output: Path,
    batch_size: int,
    *,
    sample_root: Path,
    synthetic: bool,
) -> None:
    if not synthetic:
        sample_path = sample_root / dataset / "edges.csv"
        if not sample_path.is_file():
            subprocess.run(
                [
                    "python3",
                    "scripts/fetch_u280_dataset_samples.py",
                    "--datasets",
                    dataset,
                    "--output-root",
                    str(sample_root),
                ],
                check=True,
            )
    command = [
        "python3",
        "scripts/generate_u280_comparison_fixture.py",
        "--dataset",
        dataset,
        "--model",
        model,
        "--batch-size",
        str(batch_size),
        "--output",
        str(output),
    ]
    if synthetic:
        command.append("--synthetic")
    else:
        command.extend(["--input", str(sample_root / dataset / "edges.csv")])
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def kernel_scalar_arguments(solution: str, model: str, mode: int) -> tuple[int, int, int]:
    if solution == "TempGNN":
        return 16, 1, 1
    return MODEL_IDS[model], mode, 1


def prepare_golden(
    args: argparse.Namespace,
    fixture: Path,
    *,
    fanout: int,
    depth: int,
    model: str,
) -> None:
    embedding_path = fixture / f"expected_{args.kernel_name}_embedding.bin"
    stats_path = fixture / f"expected_{args.kernel_name}_stats.bin"
    if args.solution == "TempGNN":
        if not embedding_path.is_file() or not stats_path.is_file():
            raise SystemExit(f"TempGNN golden files are missing from {fixture}")
        return
    if args.baseline_reference is None or not args.baseline_reference.is_file():
        raise SystemExit(f"{args.solution} requires --baseline-reference")
    command = [
        str(args.baseline_reference.resolve()),
        str(fixture.resolve()),
        str(fanout),
        str(depth),
        str(MODEL_IDS[model]),
        str(args.mode),
        args.solution,
        "--write",
    ]
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
        timeout=600,
    )
    (fixture / f"expected_{args.kernel_name}.log").write_text(result.stdout, encoding="utf-8")
    if not embedding_path.is_file() or not stats_path.is_file():
        raise SystemExit(f"{args.solution} reference did not write golden files")


def host_command(
    args: argparse.Namespace,
    fixture: Path,
    *,
    fanout: int,
    depth: int,
    arg13: int,
    arg14: int,
    arg15: int,
    warmup: int,
    iterations: int,
) -> list[str]:
    return [
        str(args.host.resolve()),
        str(args.xclbin.resolve()),
        str(fixture.resolve()),
        args.kernel_name,
        str(fanout),
        str(depth),
        str(arg13),
        str(arg14),
        str(arg15),
        str(args.device),
        str(warmup),
        str(iterations),
    ]


def run_with_power_sampling(
    command: list[str],
    *,
    gate_prefix: Path,
    device: str,
    power_tool: str,
    interval_s: float,
    timeout_s: float,
) -> tuple[dict[str, str], list[float]]:
    ready_path = gate_prefix.with_suffix(gate_prefix.suffix + ".ready")
    go_path = gate_prefix.with_suffix(gate_prefix.suffix + ".go")
    ready_path.unlink(missing_ok=True)
    go_path.unlink(missing_ok=True)
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    powers: list[float] = []
    deadline = time.monotonic() + timeout_s
    ready_deadline = min(deadline, time.monotonic() + 180.0)
    while not ready_path.is_file() and process.poll() is None:
        if time.monotonic() > ready_deadline:
            process.kill()
            raise SystemExit(f"host did not reach the measurement gate: {' '.join(command)}")
        time.sleep(0.02)
    if process.poll() is not None:
        stdout = process.stdout.read() if process.stdout is not None else ""
        raise subprocess.CalledProcessError(process.returncode, command, output=stdout)
    go_path.write_text("go\n", encoding="ascii")
    while process.poll() is None:
        if time.monotonic() > deadline:
            process.kill()
            raise SystemExit(f"hardware measurement timed out: {' '.join(command)}")
        sample = read_board_power(power_tool, device)
        if sample is not None:
            powers.append(sample)
        time.sleep(interval_s)
    stdout = process.stdout.read() if process.stdout is not None else ""
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command, output=stdout)
    if not powers:
        sample = read_board_power(power_tool, device)
        if sample is not None:
            powers.append(sample)
    ready_path.unlink(missing_ok=True)
    go_path.unlink(missing_ok=True)
    return parse_host_output(stdout), powers


def read_board_power(power_tool: str, device: str) -> float | None:
    result = subprocess.run(
        [power_tool, "examine", "--device", device, "--report", "electrical"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=False,
    )
    match = POWER_PATTERN.search(result.stdout)
    return float(match.group(1)) if match else None


def resolve_power_device(power_tool: str, requested: str) -> str:
    if re.fullmatch(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]", requested):
        return requested
    try:
        index = int(requested)
    except ValueError as exc:
        raise SystemExit(f"invalid XRT device index/BDF: {requested}") from exc
    result = subprocess.run(
        [power_tool, "examine"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=True,
    )
    devices = BDF_PATTERN.findall(result.stdout)
    if not 0 <= index < len(devices):
        raise SystemExit(f"device index {index} is outside the {len(devices)} detected XRT devices")
    return devices[index]


def read_packaged_clock_evidence(
    path: Path, *, kernel_name: str, target_mhz: float
) -> dict[str, float]:
    xclbinutil = shutil.which("xclbinutil")
    if not xclbinutil:
        raise SystemExit("xclbinutil is required to verify the linked kernel frequency")
    result = subprocess.run(
        [xclbinutil, "--info", "--input", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=True,
    )
    link_requested = parse_xclbin_link_requested_frequency(result.stdout, kernel_name)
    provenance_path = path.parent.parent / "evidence" / "build_provenance.json"
    if not provenance_path.is_file():
        raise SystemExit(f"packaged clock provenance is missing: {provenance_path}")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get("kernel") != kernel_name:
        raise SystemExit(f"clock provenance kernel does not match {kernel_name}")
    if provenance.get("distributed_xclbin_sha256") != sha256_file(path):
        raise SystemExit("clock provenance xclbin hash does not match the measured file")
    recorded_link = float(provenance["xclbin_link_requested_frequency_mhz"])
    post_route_frequency = float(provenance["post_route_kernel_frequency_mhz"])
    post_route_wns = float(provenance["post_route_wns_ns"])
    post_route_tns = float(provenance["post_route_tns_ns"])
    if abs(link_requested - recorded_link) > 1e-6:
        raise SystemExit("xclbin link frequency disagrees with packaged provenance")
    for label, value in (
        ("xclbin link request", link_requested),
        ("post-route kernel clock", post_route_frequency),
    ):
        if abs(value - target_mhz) > 0.5:
            raise SystemExit(f"{label} is {value:.3f} MHz, expected {target_mhz:.3f} MHz")
    if provenance.get("post_route_timing_met") is not True or post_route_wns < 0 or post_route_tns < 0:
        raise SystemExit("packaged post-route timing evidence does not pass")
    return {
        "xclbin_link_requested_frequency_mhz": link_requested,
        "post_route_frequency_mhz": post_route_frequency,
        "post_route_wns_ns": post_route_wns,
        "post_route_tns_ns": post_route_tns,
    }


def parse_xclbin_link_requested_frequency(output: str, kernel_name: str) -> float:
    instance = f"{kernel_name}_1"
    frequencies = {
        int(match.group("hz")) / 1_000_000.0
        for match in XCLBIN_LINK_FREQ_PATTERN.finditer(output)
        if match.group("instance") == instance
    }
    if len(frequencies) != 1:
        raise SystemExit(
            f"xclbin metadata must report one --freqhz value for {instance}; found {sorted(frequencies)}"
        )
    return frequencies.pop()


def parse_vivado_kernel_clock(output: str, kernel_name: str) -> tuple[float, float]:
    instance = f"{kernel_name}_1"
    matches = [
        match
        for match in VIVADO_KERNEL_CLOCK_PATTERN.finditer(output)
        if match.group("instance_path").rsplit("/", 1)[-1] == instance
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"Vivado log must report one ap_clk connection for {instance}; found {len(matches)}"
        )
    return float(matches[0].group("requested")), float(matches[0].group("implemented"))


def parse_post_route_timing(output: str) -> tuple[float, float]:
    section = output.split("Design Timing Summary", 1)
    if len(section) != 2:
        raise SystemExit("post-route report does not contain Design Timing Summary")
    match = DESIGN_TIMING_PATTERN.search(section[1])
    if not match:
        raise SystemExit("post-route report does not contain parseable WNS/TNS values")
    return float(match.group("wns")), float(match.group("tns"))


def parse_host_output(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line or line.startswith("stat["):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    missing = sorted(REQUIRED_HOST_KEYS - set(values))
    if missing:
        raise SystemExit(f"host output is missing {', '.join(missing)}:\n{output}")
    return values


def write_evidence(
    prefix: Path,
    *,
    command: list[str],
    calibration_command: list[str],
    host_values: dict[str, str],
    powers: list[float],
    row: dict[str, object],
) -> None:
    payload = {
        "schema_version": 1,
        "command": portable_command(command),
        "calibration_command": portable_command(calibration_command),
        "host_values": host_values,
        "power_samples_w": powers,
        "csv_row": row,
    }
    prefix.with_suffix(".json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def portable_command(command: list[str]) -> list[str]:
    repo_root = str(Path(__file__).resolve().parents[1])
    home = str(Path.home())
    portable = []
    for argument in command:
        value = argument.replace(repo_root, "{repo}")
        if home and home != repo_root:
            value = value.replace(home, "{home}")
        portable.append(value)
    return portable


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
