#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.measure_u280_forward import (
    parse_post_route_timing,
    parse_vivado_kernel_clock,
    parse_xclbin_link_requested_frequency,
)


SYSTEMS = {
    "TempGNN": ("tempgnn_forward_kernel", "tempgnn_forward_kernel.hw.xclbin"),
    "MATG": ("matg_kernel", "matg_kernel.hw.xclbin"),
    "ViTeGNN": ("vitegnn_kernel", "vitegnn_kernel.hw.xclbin"),
    "RTGA": ("rtga_kernel", "rtga_kernel.hw.xclbin"),
}

REPORT_PATTERNS = {
    "post_route_timing.rpt": (
        "**/dr_timing_summary.rpt",
        "**/*timing_summary_routed.rpt",
        "**/*timing_summary*.rpt",
    ),
    "post_route_utilization.rpt": (
        "**/*kernel_util_routed.rpt",
        "**/*kernel_util_placed.rpt",
        "**/*full_util_routed.rpt",
        "**/*full_util_placed.rpt",
        "**/*utilization_placed.rpt",
        "**/*utilization_routed.rpt",
        "**/*utilization*.rpt",
    ),
    "route_status.rpt": ("**/*route_status.rpt",),
    "xclbin_link_summary.txt": ("*.xclbin.link_summary",),
    "xclbin_info.txt": ("*.xclbin.info",),
    "vitis_link_steps.log": ("**/link.steps.log",),
    "vivado_implementation.log": ("**/logs/link/vivado.log", "**/impl_1/runme.log"),
    "kernel_hls_synthesis.rpt": (
        "**/hls/syn/report/{kernel}_csynth.rpt",
        "**/{kernel}_csynth.rpt",
    ),
    "vitis_hls_compile.log": ("**/logs/hls_compile.log", "**/vitis_hls.log"),
}

REQUIRED_REPORTS = frozenset(
    {
        "post_route_timing.rpt",
        "post_route_utilization.rpt",
        "xclbin_link_summary.txt",
        "vitis_link_steps.log",
        "vivado_implementation.log",
        "kernel_hls_synthesis.rpt",
        "vitis_hls_compile.log",
    }
)


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    builds = parse_assignments(args.build, "--build", required=set(SYSTEMS))
    logs = parse_assignments(args.build_log, "--build-log")
    config_path = repo_root / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config_by_system = {item["name"]: item for item in config["systems"]}

    if not args.host.is_file():
        raise SystemExit(f"common XRT host does not exist: {args.host}")
    if not args.baseline_reference.is_file():
        raise SystemExit(f"baseline C-sim reference does not exist: {args.baseline_reference}")
    xclbinutil = shutil.which(args.xclbinutil)
    if not xclbinutil:
        raise SystemExit("xclbinutil is required to anonymize packaged xclbin metadata")

    redactions = redaction_map(repo_root)
    out_root = repo_root / args.out
    aggregate: dict[str, object] = {
        "schema_version": 1,
        "paper_id": config.get("paper_id", "pap142"),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "platform": config.get("platform"),
        "config_sha256": sha256_file(config_path),
        "metadata_normalization": (
            "Absolute build paths, login names, and build host names are replaced in the xclbin "
            "BUILD_METADATA and SYSTEM_METADATA sections for double-blind review; "
            "the FPGA BITSTREAM section is verified byte-identical before and after normalization."
        ),
        "systems": [],
    }
    aggregate_evidence = out_root / "evidence"
    if aggregate_evidence.exists():
        shutil.rmtree(aggregate_evidence)
    if args.baseline_validation_log is not None:
        if not args.baseline_validation_log.is_file():
            raise SystemExit(
                f"baseline validation log does not exist: {args.baseline_validation_log}"
            )
        aggregate_evidence.mkdir(parents=True, exist_ok=True)
        validation_out = aggregate_evidence / "baseline_csim_real24.log"
        copy_sanitized_text(args.baseline_validation_log, validation_out, redactions)
        aggregate["baseline_validation_log"] = {
            "path": str(validation_out.relative_to(repo_root)),
            "sha256": sha256_file(validation_out),
        }

    for system, (kernel, xclbin_name) in SYSTEMS.items():
        build_dir = builds[system].resolve()
        raw_xclbin = build_dir / xclbin_name
        if not raw_xclbin.is_file():
            raise SystemExit(f"{system}: missing xclbin: {raw_xclbin}")

        system_root = out_root / system
        bin_dir = system_root / "bin"
        evidence_dir = system_root / "evidence"
        for generated_dir in (bin_dir, evidence_dir):
            if generated_dir.exists():
                shutil.rmtree(generated_dir)
        bin_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        distributed_xclbin = bin_dir / xclbin_name

        bitstream_sha = anonymize_xclbin(
            raw_xclbin,
            distributed_xclbin,
            xclbinutil=xclbinutil,
            redactions=redactions,
        )
        host_out = bin_dir / "u280_forward_benchmark_host"
        shutil.copy2(args.host, host_out)
        ensure_binary_is_anonymous(host_out, redactions)
        if system != "TempGNN":
            reference_out = bin_dir / "baseline_csim"
            shutil.copy2(args.baseline_reference, reference_out)
            ensure_binary_is_anonymous(reference_out, redactions)

        evidence_files: dict[str, str] = {}
        for output_name, patterns in REPORT_PATTERNS.items():
            expanded_patterns = tuple(pattern.format(kernel=kernel) for pattern in patterns)
            source = find_report(build_dir, expanded_patterns)
            if source is None:
                continue
            destination = evidence_dir / output_name
            copy_sanitized_text(source, destination, redactions)
            evidence_files[output_name] = sha256_file(destination)
        validate_required_reports(system, evidence_files)

        build_log = logs.get(system)
        if build_log is not None:
            if not build_log.is_file():
                raise SystemExit(f"{system}: build log does not exist: {build_log}")
            destination = evidence_dir / "vitis_link.log"
            copy_sanitized_text(build_log, destination, redactions)
            evidence_files[destination.name] = sha256_file(destination)

        info = subprocess.run(
            [xclbinutil, "--info", "--input", str(distributed_xclbin)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout
        info_path = evidence_dir / "packaged_xclbin_info.txt"
        info_path.write_text(redact_text(info, redactions), encoding="utf-8")
        evidence_files[info_path.name] = sha256_file(info_path)
        expected_frequency = float(config.get("requested_frequency_mhz", 225))
        frequency_tolerance = float(config.get("frequency_comparison_tolerance_mhz", 0.5))
        xclbin_requested_mhz = parse_xclbin_link_requested_frequency(info, kernel)
        vivado_requested_mhz, post_route_frequency_mhz = parse_vivado_kernel_clock(
            (evidence_dir / "vivado_implementation.log").read_text(encoding="utf-8"), kernel
        )
        post_route_wns_ns, post_route_tns_ns = parse_post_route_timing(
            (evidence_dir / "post_route_timing.rpt").read_text(encoding="utf-8")
        )
        for label, frequency in (
            ("xclbin link request", xclbin_requested_mhz),
            ("Vivado kernel request", vivado_requested_mhz),
            ("post-route kernel clock", post_route_frequency_mhz),
        ):
            if abs(frequency - expected_frequency) > frequency_tolerance:
                raise SystemExit(
                    f"{system}: {label} is {frequency:.3f} MHz, expected "
                    f"{expected_frequency:.3f} MHz"
                )
        if post_route_wns_ns < 0 or post_route_tns_ns < 0:
            raise SystemExit(
                f"{system}: post-route timing failed: WNS={post_route_wns_ns:.3f} ns, "
                f"TNS={post_route_tns_ns:.3f} ns"
            )

        system_config = config_by_system[system]
        source_hashes = {
            source: sha256_file(repo_root / source) for source in system_config["sources"]
        }
        build_source_hashes = {
            source: sha256_file(repo_root / source)
            for source in system_config.get("build_sources", system_config["sources"])
        }
        provenance = {
            "schema_version": 1,
            "paper_id": config.get("paper_id", "pap142"),
            "system": system,
            "kernel": kernel,
            "source_revision": system_config["source_revision"],
            "platform": config.get("platform"),
            "requested_frequency_mhz": config.get("requested_frequency_mhz", 225),
            "xclbin_link_requested_frequency_mhz": xclbin_requested_mhz,
            "vivado_kernel_requested_frequency_mhz": vivado_requested_mhz,
            "post_route_kernel_frequency_mhz": post_route_frequency_mhz,
            "post_route_wns_ns": post_route_wns_ns,
            "post_route_tns_ns": post_route_tns_ns,
            "post_route_timing_met": True,
            "config_sha256": sha256_file(config_path),
            "source_files_sha256": source_hashes,
            "build_input_files_sha256": build_source_hashes,
            "raw_build_xclbin_sha256": sha256_file(raw_xclbin),
            "distributed_xclbin_sha256": sha256_file(distributed_xclbin),
            "bitstream_section_sha256": bitstream_sha,
            "common_host_sha256": sha256_file(host_out),
            "baseline_reference_sha256": (
                sha256_file(bin_dir / "baseline_csim") if system != "TempGNN" else None
            ),
            "evidence_files_sha256": evidence_files,
            "metadata_normalized_for_double_blind_review": True,
        }
        provenance_path = evidence_dir / "build_provenance.json"
        provenance_path.write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        aggregate["systems"].append(provenance)

    manifest_path = out_root / "build_manifest.json"
    manifest_path.write_text(
        json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(manifest_path.resolve())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage four U280 artifacts and sanitized post-route provenance."
    )
    parser.add_argument(
        "--build",
        action="append",
        required=True,
        metavar="SYSTEM=PATH",
        help="repeat for TempGNN, MATG, ViTeGNN, and RTGA",
    )
    parser.add_argument("--build-log", action="append", default=[], metavar="SYSTEM=PATH")
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--baseline-reference", type=Path, required=True)
    parser.add_argument("--baseline-validation-log", type=Path)
    parser.add_argument("--config", type=Path, default=Path("configs/u280_core_reproduction.json"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/u280"))
    parser.add_argument("--xclbinutil", default="xclbinutil")
    return parser.parse_args()


def parse_assignments(
    values: list[str], label: str, *, required: set[str] | None = None
) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"{label} must use SYSTEM=PATH: {value!r}")
        name, raw_path = value.split("=", 1)
        if name not in SYSTEMS:
            raise SystemExit(f"{label} has unknown system {name!r}")
        if name in parsed:
            raise SystemExit(f"{label} repeats {name}")
        parsed[name] = Path(raw_path)
    missing = sorted((required or set()) - set(parsed))
    if missing:
        raise SystemExit(f"{label} is missing: {', '.join(missing)}")
    return parsed


def redaction_map(repo_root: Path) -> dict[str, str]:
    home = Path.home()
    user = getpass.getuser()
    hostname = socket.gethostname()
    return {
        str(repo_root): "/home/ae_reviewer/TempGNN",
        str(home): "/home/ae_reviewer",
        hostname: "u280-ae-host",
        user: "ae_reviewer",
    }


def redact_text(text: str, redactions: dict[str, str]) -> str:
    for original, replacement in sorted(redactions.items(), key=lambda item: -len(item[0])):
        if original:
            text = text.replace(original, replacement)
    return text


def anonymize_xclbin(
    source: Path,
    destination: Path,
    *,
    xclbinutil: str,
    redactions: dict[str, str],
) -> str:
    with tempfile.TemporaryDirectory(prefix="pap142_xclbin_") as temporary:
        temp = Path(temporary)
        source_bitstream = temp / "source.bit"
        destination_bitstream = temp / "destination.bit"
        replacements: list[str] = []
        for section, section_format, suffix in (
            ("BUILD_METADATA", "JSON", "json"),
            ("SYSTEM_METADATA", "RAW", "json"),
        ):
            metadata = temp / f"{section.lower()}.{suffix}"
            sanitized_metadata = temp / f"{section.lower()}_sanitized.{suffix}"
            run_xclbinutil(
                xclbinutil,
                "--dump-section",
                f"{section}:{section_format}:{metadata}",
                "--input",
                str(source),
                "--force",
            )
            sanitized_metadata.write_text(
                redact_text(metadata.read_text(encoding="utf-8"), redactions),
                encoding="utf-8",
            )
            replacements.extend(
                ["--replace-section", f"{section}:{section_format}:{sanitized_metadata}"]
            )
        run_xclbinutil(
            xclbinutil,
            *replacements,
            "--input",
            str(source),
            "--output",
            str(destination),
            "--force",
        )
        run_xclbinutil(
            xclbinutil,
            "--dump-section",
            f"BITSTREAM:RAW:{source_bitstream}",
            "--input",
            str(source),
            "--force",
        )
        run_xclbinutil(
            xclbinutil,
            "--dump-section",
            f"BITSTREAM:RAW:{destination_bitstream}",
            "--input",
            str(destination),
            "--force",
        )
        source_sha = sha256_file(source_bitstream)
        destination_sha = sha256_file(destination_bitstream)
        if source_sha != destination_sha:
            raise SystemExit(f"{source.name}: xclbin metadata normalization changed the bitstream")
    ensure_binary_is_anonymous(destination, redactions)
    return source_sha


def run_xclbinutil(executable: str, *arguments: str) -> None:
    subprocess.run(
        [executable, *arguments],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def ensure_binary_is_anonymous(path: Path, redactions: dict[str, str]) -> None:
    payload = path.read_bytes()
    leaked = [token for token in redactions if token and token.encode() in payload]
    if leaked:
        raise SystemExit(f"{path}: double-blind build metadata remains: {leaked}")


def find_report(build_dir: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        matches = [path for path in build_dir.glob(pattern) if path.is_file()]
        if matches:
            return max(matches, key=lambda path: (path.stat().st_mtime_ns, path.stat().st_size))
    return None


def validate_required_reports(system: str, evidence_files: dict[str, str]) -> None:
    missing = sorted(REQUIRED_REPORTS - evidence_files.keys())
    if missing:
        raise SystemExit(f"{system}: missing required build evidence: {', '.join(missing)}")


def copy_sanitized_text(source: Path, destination: Path, redactions: dict[str, str]) -> None:
    text = source.read_text(encoding="utf-8", errors="replace")
    destination.write_text(redact_text(text, redactions), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
