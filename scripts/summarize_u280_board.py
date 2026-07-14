from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


STAT_RE = re.compile(r"stat\[(\d+)\]=(\d+)")


def main() -> None:
    args = parse_args()
    summary = {
        "platform": "U280",
        "board": "Alveo U280",
        "hostname": parse_hostname(args.board_log),
        "device": "xcu280-fsvh2892-2L-e",
        "shell": parse_shell(args.board_log),
        "xrt_version": parse_xrt(args.board_log),
        "vitis_version": "2023.2",
        "platform_vbnv": parse_platform_vbnv(args.xclbin_info),
        "xclbin": str(args.xclbin),
        "host_binary": str(args.host_binary),
        "build_log": str(args.board_log) if args.board_log.exists() else None,
        "config": infer_config_name(args.board_dir, args.xclbin),
        "requested_kernel_freq_mhz": 225,
        "clocks": parse_clocks(args.xclbin_info),
        "post_route_timing": parse_timing(args.timing_report),
        "resource_stage": infer_resource_stage(args.kernel_util_report, args.full_util_report),
        "resources": {
            "kernel": parse_kernel_util(args.kernel_util_report),
            "full_design": parse_full_util(args.full_util_report),
        },
        "hls_system_estimate": parse_system_estimate(args.system_estimate_report),
        "tests": parse_tests(args.board_dir),
        "layout": parse_layout(args.board_dir),
        "source_files": {
            "board_log": str(args.board_log) if args.board_log.exists() else None,
            "timing_report": str(args.timing_report) if args.timing_report.exists() else None,
            "kernel_util_report": str(args.kernel_util_report) if args.kernel_util_report.exists() else None,
            "full_util_report": str(args.full_util_report) if args.full_util_report.exists() else None,
            "system_estimate_report": str(args.system_estimate_report) if args.system_estimate_report.exists() else None,
            "xclbin_info": str(args.xclbin_info) if args.xclbin_info.exists() else None,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize measured U280 board and routed-build evidence.")
    parser.add_argument("--board-dir", type=Path, default=Path("results/board_u280"))
    parser.add_argument("--board-log", type=Path, default=Path("logs/u280_board_run_20260703_161208.log"))
    parser.add_argument(
        "--xclbin",
        type=Path,
        default=Path("artifacts/u280/TempGNN/bin/tempgnn_forward_kernel.hw.xclbin"),
    )
    parser.add_argument(
        "--host-binary",
        type=Path,
        default=Path("artifacts/u280/TempGNN/bin/u280_forward_benchmark_host"),
    )
    parser.add_argument(
        "--xclbin-info",
        type=Path,
        default=Path("artifacts/u280/TempGNN/evidence/packaged_xclbin_info.txt"),
    )
    parser.add_argument("--timing-report", type=Path, default=Path("hardware/vitis/_x/reports/link/imp/impl_1_hw_bb_locked_timing_summary_routed.rpt"))
    parser.add_argument("--kernel-util-report", type=Path, default=Path("hardware/vitis/_x/reports/link/imp/impl_1_kernel_util_routed.rpt"))
    parser.add_argument("--full-util-report", type=Path, default=Path("hardware/vitis/_x/reports/link/imp/impl_1_full_util_routed.rpt"))
    parser.add_argument("--system-estimate-report", type=Path, default=Path("hardware/vitis/_x/reports/tempgnn_forward_kernel.hw/system_estimate_tempgnn_forward_kernel.hw.xtxt"))
    parser.add_argument("--out", type=Path, default=Path("results/board_u280/summary.json"))
    return parser.parse_args()


def read_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def parse_hostname(path: Path) -> str | None:
    match = re.search(r"^HOST\s+(.+)$", read_text(path), re.MULTILINE)
    return match.group(1).strip() if match else None


def parse_shell(path: Path) -> str | None:
    text = read_text(path)
    match = re.search(r"\[\S+\]\s+:\s+(\S+)\s+", text)
    return match.group(1) if match else None


def parse_xrt(path: Path) -> str | None:
    match = re.search(r"Version\s+:\s+([^\r\n]+)", read_text(path))
    return match.group(1).strip() if match else None


def infer_config_name(board_dir: Path, xclbin: Path) -> str:
    lower = f"{board_dir} {xclbin}".lower()
    if "fullsize" in lower:
        return "u280-fullsize-buffer-envelope"
    if "u55c" in lower:
        return "u55c-forward-path"
    return "u280-forward-path"


def infer_resource_stage(kernel_report: Path, full_report: Path) -> str | None:
    report_names = f"{kernel_report} {full_report}".lower()
    if "routed" in report_names or "impl_1_hw_bb_locked" in report_names:
        return "post-route"
    if "placed" in report_names:
        return "placed"
    if "synthed" in report_names or "synth" in report_names:
        return "synthesized"
    if kernel_report.exists() or full_report.exists():
        return "available"
    return None


def parse_platform_vbnv(path: Path) -> str | None:
    match = re.search(r"Platform VBNV:\s+(\S+)", read_text(path))
    return match.group(1) if match else None


def parse_clocks(path: Path) -> dict[str, str]:
    text = read_text(path)
    clocks: dict[str, str] = {}
    block_re = re.compile(r"Name:\s+([^\n]+)\n\s+Index:\s+\d+\n\s+Type:\s+[^\n]+\n\s+Frequency:\s+([^\n]+)", re.MULTILINE)
    for name, freq in block_re.findall(text):
        clocks[name.strip()] = freq.strip()
    return clocks


def parse_timing(path: Path) -> dict[str, float | bool | str] | dict:
    text = read_text(path)
    if not text:
        return {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 12 and looks_float(parts[0]) and looks_float(parts[1]) and looks_float(parts[4]) and looks_float(parts[5]):
            wns = float(parts[0])
            tns = float(parts[1])
            whs = float(parts[4])
            ths = float(parts[5])
            return {
                "wns_ns": wns,
                "tns_ns": tns,
                "whs_ns": whs,
                "ths_ns": ths,
                "timing_met": wns >= 0 and tns == 0 and whs >= 0 and ths == 0,
                "source": str(path),
            }
    return {"source": str(path)}


def parse_kernel_util(path: Path) -> dict:
    text = read_text(path)
    for line in text.splitlines():
        if "| tempgnn_forward_kernel" not in line or "tempgnn_forward_kernel_1" in line:
            continue
        values = extract_util_values(line)
        if values:
            return util_dict(values)
    return {}


def parse_full_util(path: Path) -> dict:
    text = read_text(path)
    mapping = {
        "CLB LUTs": ("lut", "lut_pct"),
        "CLB Registers": ("ff", "ff_pct"),
        "Block RAM Tile": ("bram", "bram_pct"),
        "URAM": ("uram", "uram_pct"),
        "DSPs": ("dsp", "dsp_pct"),
    }
    out: dict[str, float | int] = {}
    for line in text.splitlines():
        for label, (used_key, pct_key) in mapping.items():
            if used_key in out:
                continue
            if f"| {label}" not in line:
                continue
            cols = [part.strip() for part in line.strip().strip("|").split("|")]
            if len(cols) >= 5:
                out[used_key] = int(cols[1].split()[0])
                pct = cols[-1].replace("<", "").strip()
                if looks_float(pct):
                    out[pct_key] = float(pct)
    return out


def parse_system_estimate(path: Path) -> dict:
    text = read_text(path)
    if not text:
        return {}
    out: dict[str, object] = {"source": str(path)}
    target_clock = re.search(r"Target Clock:\s+([0-9.]+)MHz", text)
    if target_clock:
        out["target_clock_mhz"] = float(target_clock.group(1))

    section = None
    top_fmax = None
    top_area: dict[str, float | int] = {}
    for line in text.splitlines():
        if line.startswith("Timing Information"):
            section = "timing"
            continue
        if line.startswith("Latency Information"):
            section = None
            continue
        if line.startswith("Area Information"):
            section = "area"
            continue
        if line.startswith("---------------"):
            continue
        cols = re.split(r"\s{2,}", line.strip())
        if section == "timing" and len(cols) >= 5 and cols[2] == "tempgnn_forward_kernel":
            if looks_float(cols[4]):
                top_fmax = float(cols[4])
        if section == "area" and len(cols) >= 8 and cols[2] == "tempgnn_forward_kernel":
            top_area = {
                "ff": int(cols[3]),
                "lut": int(cols[4]),
                "dsp": int(cols[5]),
                "bram18": int(cols[6]),
                "bram_tile_equiv": int(cols[6]) / 2.0,
                "bram_tile_pct_u280": (int(cols[6]) / 2.0) / 2016.0 * 100.0,
                "uram": int(cols[7]),
                "uram_pct_u280": int(cols[7]) / 960.0 * 100.0,
            }
    if top_fmax is not None:
        out["estimated_kernel_fmax_mhz"] = top_fmax
    if top_area:
        out["top_kernel_area"] = top_area
    return out


def extract_util_values(line: str) -> list[tuple[int, float]]:
    values: list[tuple[int, float]] = []
    for used, pct in re.findall(r"(\d+)\s+\[\s*([0-9.]+)%\]", line):
        values.append((int(used), float(pct)))
    return values


def util_dict(values: list[tuple[int, float]]) -> dict:
    keys = ["lut", "lutasmem", "ff", "bram", "uram", "dsp"]
    out: dict[str, float | int] = {}
    for key, (used, pct) in zip(keys, values):
        out[key] = used
        out[f"{key}_pct"] = pct
    return out


def parse_tests(board_dir: Path) -> list[dict]:
    tests = []
    for name in ["smoke", "tbscale", "maxbatch", "layout_smoke"]:
        path = board_dir / f"{name}.log"
        if not path.exists():
            continue
        text = read_text(path)
        stats = {int(k): int(v) for k, v in STAT_RE.findall(text)}
        kernel_time = parse_float_after("kernel_time_ms=", text)
        throughput = parse_float_after("throughput_targets_per_s=", text)
        tests.append(
            {
                "name": name,
                "targets": stats.get(0),
                "total_packets": stats.get(1),
                "unique_packets": stats.get(2),
                "kernel_time_ms": kernel_time,
                "throughput_targets_per_s": throughput,
                "expected_stats": "PASS" if "expected_stats: PASS" in text else "UNKNOWN",
                "expected_embedding": "PASS" if "expected_embedding: PASS" in text else "UNKNOWN",
                "result": "PASS" if "expected_stats: PASS" in text and "expected_embedding: PASS" in text else "CHECK",
                "log": str(path),
            }
        )
    return tests


def parse_layout(board_dir: Path) -> dict:
    png = first_existing(
        board_dir / "tempgnn_u280_fpga_layout.png",
        board_dir / "tempgnn_u280_fullsize_fpga_layout.png",
    )
    svg = first_existing(
        board_dir / "tempgnn_u280_fpga_layout.svg",
        board_dir / "tempgnn_u280_fullsize_fpga_layout.svg",
    )
    cells = board_dir / "layout_hook" / "tempgnn_u280_routed_cells.csv"
    dcp = board_dir / "layout_hook" / "tempgnn_u280_routed.dcp"
    summary = board_dir / "layout_hook" / "tempgnn_u280_layout_hook_summary.txt"
    return {
        "png": str(png) if png and png.exists() else None,
        "svg": str(svg) if svg and svg.exists() else None,
        "cells_csv": str(cells) if cells.exists() else None,
        "routed_dcp": str(dcp) if dcp.exists() else None,
        "hook_summary": str(summary) if summary.exists() else None,
    }


def first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return paths[0] if paths else None


def parse_float_after(prefix: str, text: str) -> float | None:
    match = re.search(re.escape(prefix) + r"([0-9.]+)", text)
    return float(match.group(1)) if match else None


def looks_float(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
