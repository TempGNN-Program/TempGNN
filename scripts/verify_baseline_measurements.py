from __future__ import annotations

import argparse
import csv
from pathlib import Path

from scripts.derive_comparison_figures import derive_all


BASELINES = ["MATG", "ViTeGNN", "RTGA"]


def main() -> None:
    args = parse_args()
    args.derived_dir.mkdir(parents=True, exist_ok=True)
    derive_all(args.baselines_root, args.derived_dir)

    fig10 = compare_csv(
        args.figure_dir / "fig10_speedup_tglite_cpu.csv",
        args.derived_dir / "fig10_speedup_tglite_cpu.csv",
        args.speedup_threshold,
    )
    fig11 = compare_csv(
        args.figure_dir / "fig11_speedup_matg.csv",
        args.derived_dir / "fig11_speedup_matg.csv",
        args.speedup_threshold,
    )
    fig12 = compare_csv(
        args.figure_dir / "fig12_energy_tempgnn.csv",
        args.derived_dir / "fig12_energy_tempgnn.csv",
        args.energy_threshold,
    )
    validation_rows = load_rows(args.baselines_root / "validation_summary.csv")
    summary = []
    for baseline in BASELINES:
        row = next(item for item in validation_rows if item["baseline"] == baseline)
        status = "PASS"
        reasons = []
        if row["status"] != "PASS":
            status = "FAIL"
            reasons.append("board validation")
        if not fig11["pass"]:
            status = "FAIL"
            reasons.append("Fig.11")
        if not fig12["pass"]:
            status = "FAIL"
            reasons.append("Fig.12")
        summary.append(
            {
                "baseline": baseline,
                "board_status": row["status"],
                "fig11_speedup_mean": row["fig11_speedup_mean"],
                "fig12_energy_mean": row["fig12_energy_mean"],
                "fig10_check": "PASS" if fig10["pass"] else "FAIL",
                "fig11_check": "PASS" if fig11["pass"] else "FAIL",
                "fig12_check": "PASS" if fig12["pass"] else "FAIL",
                "max_relative_error": round(max(fig10["max_error"], fig11["max_error"], fig12["max_error"]), 8),
                "status": status,
                "reason": ",".join(reasons),
            }
        )

    write_csv(args.baselines_root / "verify_summary.csv", summary)
    write_markdown(args.baselines_root / "verify_summary.md", summary, fig10, fig11, fig12, args)
    print_summary(summary, fig10, fig11, fig12)
    if any(row["status"] != "PASS" for row in summary):
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify raw baseline measurements against generated comparison figures.")
    parser.add_argument("--baselines-root", type=Path, default=Path("results/baselines_u280"))
    parser.add_argument("--figure-dir", type=Path, default=Path("results/paper_reproduction"))
    parser.add_argument("--derived-dir", type=Path, default=Path("results/derived_comparison_figures"))
    parser.add_argument("--speedup-threshold", type=float, default=0.05)
    parser.add_argument("--energy-threshold", type=float, default=0.10)
    return parser.parse_args()


def compare_csv(expected_path: Path, actual_path: Path, threshold: float) -> dict[str, object]:
    expected = index_values(expected_path)
    actual = index_values(actual_path)
    max_error = 0.0
    worst_key = ""
    for key, expected_value in expected.items():
        actual_value = actual[key]
        denom = abs(expected_value) if expected_value else 1.0
        rel = abs(actual_value - expected_value) / denom
        if rel > max_error:
            max_error = rel
            worst_key = "|".join(key)
    return {"pass": max_error <= threshold, "max_error": max_error, "worst_key": worst_key}


def index_values(path: Path) -> dict[tuple[str, str, str], float]:
    values = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("model") == "AVG":
                continue
            values[(row["dataset"], row["model"], row["solution"])] = float(row["value"])
    return values


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(
    path: Path,
    rows: list[dict[str, object]],
    fig10: dict[str, object],
    fig11: dict[str, object],
    fig12: dict[str, object],
    args: argparse.Namespace,
) -> None:
    lines = [
        "# Baseline Verification Summary",
        "",
        "| Baseline | Board | Fig.10 | Fig.11 | Fig.12 | Max rel. error | Status |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['baseline']} | {row['board_status']} | {row['fig10_check']} | {row['fig11_check']} | {row['fig12_check']} | {row['max_relative_error']} | {row['status']} |"
        )
    lines.append("")
    lines.append(f"- Speedup threshold: +/- {args.speedup_threshold * 100:.1f}%")
    lines.append(f"- Energy threshold: +/- {args.energy_threshold * 100:.1f}%")
    lines.append(f"- Fig.10 worst key: `{fig10['worst_key']}`, max error {fig10['max_error']:.8f}")
    lines.append(f"- Fig.11 worst key: `{fig11['worst_key']}`, max error {fig11['max_error']:.8f}")
    lines.append(f"- Fig.12 worst key: `{fig12['worst_key']}`, max error {fig12['max_error']:.8f}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def print_summary(
    rows: list[dict[str, object]],
    fig10: dict[str, object],
    fig11: dict[str, object],
    fig12: dict[str, object],
) -> None:
    print("Baseline verification summary")
    for row in rows:
        print(
            f"{row['baseline']}: {row['status']} "
            f"(board={row['board_status']}, Fig11={row['fig11_speedup_mean']}, Fig12={row['fig12_energy_mean']})"
        )
    print(f"Fig10: {'PASS' if fig10['pass'] else 'FAIL'} max_error={fig10['max_error']:.8f}")
    print(f"Fig11: {'PASS' if fig11['pass'] else 'FAIL'} max_error={fig11['max_error']:.8f}")
    print(f"Fig12: {'PASS' if fig12['pass'] else 'FAIL'} max_error={fig12['max_error']:.8f}")


if __name__ == "__main__":
    main()
