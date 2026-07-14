from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from tempgenn.paper_reproduction import (
    DATASETS,
    MODELS,
    figure2_rows,
    figure4a_rows,
    figure9b_rows,
    figure10_rows,
    figure11_rows,
    figure12_rows,
    figure13_rows,
    figure14_batch_rows,
    figure14_sync_rows,
    platform_notes_as_dicts,
    reference_input_path,
)


OUT_DIR = Path("results/paper_reproduction")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    figures = {
        "fig2_execution_breakdown": figure2_rows(),
        "fig4a_branch_parallelism_ratio": figure4a_rows(),
        "fig9b_gpu_overhead_breakdown": figure9b_rows(),
        "fig10_speedup_tglite_cpu": figure10_rows(),
        "fig11_speedup_matg": figure11_rows(),
        "fig12_energy_tempgnn": figure12_rows(),
        "fig13_ablation_time": figure13_rows(),
        "fig14a_batch_sensitivity": figure14_batch_rows(),
        "fig14b_tdp_entries": figure14_sync_rows(),
    }

    figure_titles = {
        "fig2_execution_breakdown": "Fig.2 execution-time breakdown",
        "fig4a_branch_parallelism_ratio": "Fig.4(a) branch parallelism ratio",
        "fig9b_gpu_overhead_breakdown": "Fig.9(b) GPU overhead breakdown",
        "fig10_speedup_tglite_cpu": "Fig.10 speedup normalized to TGLite-CPU",
        "fig11_speedup_matg": "Fig.11 speedup normalized to MATG",
        "fig12_energy_tempgnn": "Fig.12 energy normalized to TempGNN",
        "fig13_ablation_time": "Fig.13 DDTC/OATS ablation",
        "fig14a_batch_sensitivity": "Fig.14(a) batch-size sensitivity",
        "fig14b_tdp_entries": "Fig.14(b) TDP-entry sensitivity",
    }

    for name, rows in figures.items():
        _write_csv(OUT_DIR / f"{name}.csv", rows)

    _write_grouped_bar_svg(
        OUT_DIR / "fig2_execution_breakdown.svg",
        figures["fig2_execution_breakdown"],
        ["TGS (%)", "MG (%)", "VMU (%)", "TA (%)"],
        "Paper-reference Fig.2 execution-time breakdown",
    )
    _write_grouped_bar_svg(
        OUT_DIR / "fig4a_branch_parallelism_ratio.svg",
        figures["fig4a_branch_parallelism_ratio"],
        ["BPR (%)"],
        "Paper-reference Fig.4(a) branch parallelism ratio",
    )
    _write_grouped_bar_svg(
        OUT_DIR / "fig9b_gpu_overhead_breakdown.svg",
        figures["fig9b_gpu_overhead_breakdown"],
        ["Warp divergence", "Dependency synchronization", "Dynamic dependency bookkeeping"],
        "Paper-reference Fig.9(b) GPU overhead breakdown",
    )
    _write_grouped_bar_svg(
        OUT_DIR / "fig10_speedup_tglite_cpu.svg",
        figures["fig10_speedup_tglite_cpu"],
        ["TGLite-CPU", "Cascade", "TempGNN-G", "TempGNN"],
        "Paper-reference Fig.10 speedup normalized to TGLite-CPU",
    )
    _write_grouped_bar_svg(
        OUT_DIR / "fig11_speedup_matg.svg",
        figures["fig11_speedup_matg"],
        ["MATG", "ViTeGNN", "RTGA", "TempGNN"],
        "Paper-reference Fig.11 speedup normalized to MATG",
    )
    _write_grouped_bar_svg(
        OUT_DIR / "fig12_energy_tempgnn.svg",
        figures["fig12_energy_tempgnn"],
        ["TGLite-CPU", "Cascade", "MATG", "ViTeGNN", "RTGA", "TempGNN"],
        "Paper-reference Fig.12 energy normalized to TempGNN",
    )
    _write_grouped_bar_svg(
        OUT_DIR / "fig13_ablation_time.svg",
        figures["fig13_ablation_time"],
        ["TempGNN", "WO/DDTC", "WO/OATS"],
        "Paper-reference Fig.13 TempGNN with and without DDTC/OATS",
    )
    _write_line_svg(
        OUT_DIR / "fig14a_batch_sensitivity.svg",
        figures["fig14a_batch_sensitivity"],
        "Paper-reference Fig.14(a) sensitivity to batch size",
        x_label="batch size",
    )
    _write_line_svg(
        OUT_DIR / "fig14b_tdp_entries.svg",
        figures["fig14b_tdp_entries"],
        "Paper-reference Fig.14(b) sensitivity to TDP synchronization entries",
        x_label="TDP entries",
    )

    notes = platform_notes_as_dicts()
    _write_figure_data_manifest(OUT_DIR, figure_titles)
    _write_combined_figure_data(OUT_DIR, figures)
    (OUT_DIR / "baseline_sources.md").write_text(_format_notes(notes), encoding="utf-8")
    print(f"Wrote paper reproduction artifacts to {OUT_DIR.resolve()}")


def _write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_figure_data_manifest(out_dir: Path, figure_titles: Dict[str, str]) -> None:
    rows = []
    for figure_id, title in figure_titles.items():
        rows.append(
            {
                "figure_id": figure_id,
                "title": title,
                "csv_file": f"{figure_id}.csv",
                "svg_file": f"{figure_id}.svg",
                "input_file": reference_input_path().relative_to(reference_input_path().parents[1]).as_posix(),
                "data_status": "paper-reference reconstruction; not a fresh execution",
            }
        )
    _write_csv(out_dir / "figure_data_manifest.csv", rows)


def _write_combined_figure_data(out_dir: Path, figures: Dict[str, List[Dict[str, object]]]) -> None:
    rows: List[Dict[str, object]] = []
    for figure_id, figure_rows in figures.items():
        for row in figure_rows:
            merged = {"figure_id": figure_id}
            merged.update(row)
            rows.append(merged)
    _write_csv(out_dir / "all_figure_data.csv", rows)


def _category_order(rows: Sequence[Dict[str, object]]) -> List[tuple[str, str]]:
    present = {(str(row["model"]), str(row["dataset"])) for row in rows}
    preferred = [(model, dataset) for model in MODELS for dataset in DATASETS]
    preferred.extend(("ALL", dataset) for dataset in DATASETS)
    preferred.append(("AVG", "AVG"))
    ordered = [category for category in preferred if category in present]
    extras = sorted(present - set(ordered))
    return ordered + extras


def _write_grouped_bar_svg(
    path: Path,
    rows: Sequence[Dict[str, object]],
    solutions: Sequence[str],
    title: str,
) -> None:
    categories = _category_order(rows)
    values = {
        (str(row["model"]), str(row["dataset"]), str(row["solution"])): float(row["value"])
        for row in rows
    }
    max_value = max(values.values()) if values else 1.0
    width = max(1600, 70 * len(categories))
    height = 560
    margin_left = 70
    margin_bottom = 115
    margin_top = 45
    plot_w = width - margin_left - 30
    plot_h = height - margin_top - margin_bottom
    group_w = plot_w / len(categories)
    bar_w = group_w / (len(solutions) + 1)
    colors = ["#4c78a8", "#f58518", "#54a24b", "#b279a2", "#e45756", "#72b7b2"]

    svg: List[str] = [_svg_header(width, height), f'<text x="{width/2:.1f}" y="26" text-anchor="middle" font-size="18">{_esc(title)}</text>']
    svg.append(f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{width - 20}" y2="{margin_top + plot_h}" stroke="#333"/>')
    svg.append(f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#333"/>')

    for tick in range(0, 6):
        value = max_value * tick / 5.0
        y = margin_top + plot_h - (value / max_value) * plot_h
        svg.append(f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - 20}" y2="{y:.1f}" stroke="#eee"/>')
        svg.append(f'<text x="{margin_left - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="11">{value:.1f}</text>')

    for cat_idx, (model, dataset) in enumerate(categories):
        x0 = margin_left + cat_idx * group_w
        label = "AVG" if model == "AVG" else f"{model}-{dataset}"
        svg.append(
            f'<text x="{x0 + group_w/2:.1f}" y="{height - 18}" text-anchor="end" '
            f'font-size="10" transform="rotate(-55 {x0 + group_w/2:.1f},{height - 18})">{_esc(label)}</text>'
        )
        for sol_idx, solution in enumerate(solutions):
            value = values.get((model, dataset, solution), 0.0)
            bar_h = 0 if max_value == 0 else (value / max_value) * plot_h
            x = x0 + (sol_idx + 0.5) * bar_w
            y = margin_top + plot_h - bar_h
            svg.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.85:.1f}" height="{bar_h:.1f}" '
                f'fill="{colors[sol_idx % len(colors)]}"><title>{_esc(label)} {solution}: {value:.4g}</title></rect>'
            )

    _append_legend(svg, solutions, colors, width - 620, 48)
    svg.append("</svg>\n")
    path.write_text("\n".join(svg), encoding="utf-8")


def _write_line_svg(
    path: Path,
    rows: Sequence[Dict[str, object]],
    title: str,
    x_label: str,
) -> None:
    series: Dict[str, List[tuple[float, float]]] = {}
    solution_names = {str(row["solution"]) for row in rows}
    dataset_names = {str(row["dataset"]) for row in rows}
    for row in rows:
        solution = str(row["solution"])
        dataset = str(row["dataset"])
        if len(solution_names) > 1 and len(dataset_names) == 1:
            name = solution
        elif len(solution_names) == 1:
            name = dataset
        else:
            name = f"{solution}/{dataset}"
        series.setdefault(name, []).append((float(row["x"]), float(row["value"])))
    for points in series.values():
        points.sort()

    xs = sorted({point[0] for points in series.values() for point in points})
    max_value = max(point[1] for points in series.values() for point in points)
    min_x, max_x = min(xs), max(xs)
    width, height = 760, 460
    legend_columns = min(3, len(series))
    legend_rows = (len(series) + legend_columns - 1) // legend_columns
    margin_left, margin_right, margin_bottom = 70, 30, 70
    margin_top = 55 + legend_rows * 22
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    colors = ["#4c78a8", "#f58518", "#54a24b", "#b279a2", "#e45756", "#72b7b2"]

    def x_scale(x: float) -> float:
        if max_x == min_x:
            return margin_left + plot_w / 2
        return margin_left + (x - min_x) / (max_x - min_x) * plot_w

    def y_scale(y: float) -> float:
        return margin_top + plot_h - (y / max_value) * plot_h

    svg: List[str] = [_svg_header(width, height), f'<text x="{width/2}" y="26" text-anchor="middle" font-size="18">{_esc(title)}</text>']
    svg.append(f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{width - margin_right}" y2="{margin_top + plot_h}" stroke="#333"/>')
    svg.append(f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#333"/>')
    svg.append(f'<text x="{width/2}" y="{height - 12}" text-anchor="middle" font-size="13">{_esc(x_label)}</text>')

    for x in xs:
        xx = x_scale(x)
        svg.append(f'<line x1="{xx:.1f}" y1="{margin_top + plot_h}" x2="{xx:.1f}" y2="{margin_top + plot_h + 5}" stroke="#333"/>')
        svg.append(f'<text x="{xx:.1f}" y="{margin_top + plot_h + 20}" text-anchor="middle" font-size="11">{x:g}</text>')
    for tick in range(0, 6):
        value = max_value * tick / 5.0
        yy = y_scale(value)
        svg.append(f'<line x1="{margin_left}" y1="{yy:.1f}" x2="{width - margin_right}" y2="{yy:.1f}" stroke="#eee"/>')
        svg.append(f'<text x="{margin_left - 8}" y="{yy + 4:.1f}" text-anchor="end" font-size="11">{value:.1f}</text>')

    for idx, (name, points) in enumerate(series.items()):
        color = colors[idx % len(colors)]
        coords = " ".join(f"{x_scale(x):.1f},{y_scale(y):.1f}" for x, y in points)
        svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in points:
            svg.append(f'<circle cx="{x_scale(x):.1f}" cy="{y_scale(y):.1f}" r="3.5" fill="{color}"><title>{_esc(name)} {x:g}: {y:.4g}</title></circle>')
    _append_legend(
        svg,
        list(series.keys()),
        colors,
        margin_left,
        50,
        columns=legend_columns,
        column_width=(width - margin_left - margin_right) / legend_columns,
    )
    svg.append("</svg>\n")
    path.write_text("\n".join(svg), encoding="utf-8")


def _append_legend(
    svg: List[str],
    labels: Sequence[str],
    colors: Sequence[str],
    x: float,
    y: float,
    *,
    columns: int = 3,
    column_width: float = 190,
) -> None:
    for idx, label in enumerate(labels):
        xx = x + (idx % columns) * column_width
        yy = y + (idx // columns) * 22
        svg.append(f'<rect x="{xx:.1f}" y="{yy - 10:.1f}" width="12" height="12" fill="{colors[idx % len(colors)]}"/>')
        svg.append(f'<text x="{xx + 18:.1f}" y="{yy:.1f}" font-size="12">{_esc(label)}</text>')


def _svg_header(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
    )


def _format_notes(notes: Sequence[Dict[str, str]]) -> str:
    lines = ["# Baseline Reproduction Notes", ""]
    for note in notes:
        lines.append(f"## {note['name']}")
        lines.append(f"- Platform: {note['platform']}")
        lines.append(f"- Toolchain: {note['toolchain']}")
        lines.append(f"- Reproduction status: {note['reproduction_status']}")
        lines.append(f"- Key settings: {note['key_settings']}")
        lines.append(f"- Notes: {note['notes']}")
        lines.append("")
    return "\n".join(lines)


def _esc(value: object) -> str:
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


if __name__ == "__main__":
    main()
