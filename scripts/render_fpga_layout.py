from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path


LOC_RE = re.compile(r"_X(?P<x>\d+)Y(?P<y>\d+)")


def main() -> None:
    args = parse_args()
    args.out_png.parent.mkdir(parents=True, exist_ok=True)
    summary = load_summary(args.summary)
    cells = load_cells(args.cells, args.max_cells)
    if cells:
        render_loc_layout(cells, summary, args.out_png, args.out_svg)
    else:
        render_fallback_layout(summary, args.out_png, args.out_svg)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a TempGNN U280 FPGA layout evidence figure.")
    parser.add_argument("--cells", type=Path, default=Path("results/board_u280/layout_hook/tempgnn_u280_routed_cells.csv"))
    parser.add_argument("--summary", type=Path, default=Path("results/board_u280/summary.json"))
    parser.add_argument("--out-png", type=Path, default=Path("results/board_u280/tempgnn_u280_fpga_layout.png"))
    parser.add_argument("--out-svg", type=Path, default=Path("results/board_u280/tempgnn_u280_fpga_layout.svg"))
    parser.add_argument("--max-cells", type=int, default=1_000_000)
    return parser.parse_args()


def load_summary(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def load_cells(path: Path, max_cells: int) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            match = LOC_RE.search(row.get("loc", ""))
            if not match:
                continue
            ref = row.get("ref", "")
            rows.append(
                {
                    "x": int(match.group("x")),
                    "y": int(match.group("y")),
                    "ref": ref,
                    "kind": primitive_kind(ref),
                    "is_kernel": row.get("is_kernel", "0").strip().lower() in {"1", "true", "yes"},
                }
            )
            if len(rows) >= max_cells:
                break
    return rows


def primitive_kind(ref: str) -> str:
    ref = ref.upper()
    if ref.startswith(("FD", "LUT", "MUX", "CARRY", "SRL", "RAMD", "RAMS")):
        return "logic"
    if ref.startswith("RAMB"):
        return "bram"
    if ref.startswith("URAM"):
        return "uram"
    if ref.startswith("DSP"):
        return "dsp"
    if ref.startswith(("HBM", "PCIE", "GTY", "IBUF", "OBUF", "BUFG", "MMCM", "PLL")):
        return "shell"
    return "other"


def render_loc_layout(cells: list[dict], summary: dict, out_png: Path, out_svg: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ModuleNotFoundError:
        render_loc_layout_pil(cells, summary, out_png, out_svg)
        return

    bg = "#070b16"
    grid = "#283349"
    colors = {
        "logic": "#46647f",
        "bram": "#5ea3bb",
        "uram": "#8d66c4",
        "dsp": "#d48a32",
        "shell": "#263246",
        "other": "#33435d",
    }
    kernel_color = "#ffd24a"
    kernel_edge = "#ff8c42"

    xs = [c["x"] for c in cells]
    ys = [c["y"] for c in cells]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad_x = max(8, int((max_x - min_x) * 0.03))
    pad_y = max(8, int((max_y - min_y) * 0.03))

    fig = plt.figure(figsize=(18, 11), facecolor=bg)
    ax = fig.add_axes([0.055, 0.105, 0.77, 0.78], facecolor=bg)
    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#8fa6c8")
        spine.set_linewidth(1.3)

    for frac in [1 / 3, 2 / 3]:
        y = min_y + (max_y - min_y) * frac
        ax.axhline(y, color="#8a6ad8", linewidth=1.2)
    for frac in [0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875]:
        x = min_x + (max_x - min_x) * frac
        ax.axvline(x, color=grid, linewidth=0.7, alpha=0.8)

    non_kernel = [c for c in cells if not c["is_kernel"]]
    for kind, color in colors.items():
        pts = [(c["x"], c["y"]) for c in non_kernel if c["kind"] == kind]
        if not pts:
            continue
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=1.8, marker="s", c=color, alpha=0.45, linewidths=0)

    kernel = [c for c in cells if c["is_kernel"]]
    if kernel:
        ax.scatter(
            [c["x"] for c in kernel],
            [c["y"] for c in kernel],
            s=5.0,
            marker="s",
            c=kernel_color,
            alpha=0.88,
            linewidths=0,
        )
        kxs = [c["x"] for c in kernel]
        kys = [c["y"] for c in kernel]
        kmin_x, kmax_x = min(kxs), max(kxs)
        kmin_y, kmax_y = min(kys), max(kys)
        ax.add_patch(
            Rectangle(
                (kmin_x - 3, kmin_y - 3),
                max(1, kmax_x - kmin_x + 6),
                max(1, kmax_y - kmin_y + 6),
                fill=False,
                edgecolor=kernel_edge,
                linewidth=2.0,
            )
        )
        extent = f"x={kmin_x}-{kmax_x}, y={kmin_y}-{kmax_y}"
    else:
        extent = "kernel hierarchy not tagged in LOC CSV"

    ax.text(min_x - pad_x - 0.015 * (max_x - min_x), min_y + (max_y - min_y) * 1 / 6, "SLR0", color="#9b83e6", va="center", ha="right", fontsize=10)
    ax.text(min_x - pad_x - 0.015 * (max_x - min_x), min_y + (max_y - min_y) * 3 / 6, "SLR1", color="#9b83e6", va="center", ha="right", fontsize=10)
    ax.text(min_x - pad_x - 0.015 * (max_x - min_x), min_y + (max_y - min_y) * 5 / 6, "SLR2", color="#9b83e6", va="center", ha="right", fontsize=10)

    timing = summary.get("post_route_timing", {})
    title = summary.get("layout_title", "TempGNN on Alveo U280: real post-route FPGA placement")
    subtitle = (
        f"{summary.get('platform_vbnv', 'xilinx_u280')} routed build"
        f", WNS {format_ns(timing.get('wns_ns'))}"
        f", {len(cells):,} placed primitives exported from Vivado LOC"
    )
    fig.text(0.055, 0.94, title, color="#e9eef8", fontsize=20, weight="bold")
    fig.text(0.055, 0.915, subtitle, color="#9fb0c9", fontsize=11)

    legend_ax = fig.add_axes([0.845, 0.27, 0.14, 0.57], facecolor=bg)
    legend_ax.axis("off")
    lines = [
        ("Post-route evidence", "#e9eef8", 11, "bold"),
        (f"Device  {summary.get('device', 'xcu280')}", "#b9c5d9", 8, "normal"),
        (f"Shell   {summary.get('shell', summary.get('platform_vbnv', 'U280'))}", "#b9c5d9", 8, "normal"),
        (f"Timing  WNS {format_ns(timing.get('wns_ns'))}", "#b9c5d9", 8, "normal"),
        (f"Kernel cells  {len(kernel):,}", "#b9c5d9", 8, "normal"),
        ("", "#b9c5d9", 5, "normal"),
        ("Primitive classes", "#e9eef8", 10, "bold"),
    ]
    y = 1.0
    for text, color, size, weight in lines:
        legend_ax.text(0.0, y, text, color=color, fontsize=size, weight=weight, va="top")
        y -= 0.065 if text else 0.035
    for label, color in [
        ("U280 shell/other cells", colors["shell"]),
        ("U280 LUT/FF/register", colors["logic"]),
        ("U280 BRAM", colors["bram"]),
        ("U280 URAM", colors["uram"]),
        ("U280 DSP", colors["dsp"]),
        ("TempGNN kernel cells", kernel_color),
    ]:
        legend_ax.add_patch(Rectangle((0.0, y - 0.018), 0.08, 0.028, color=color, alpha=0.9))
        legend_ax.text(0.11, y, label, color="#cbd6e6", fontsize=8, va="center")
        y -= 0.055
    legend_ax.text(0.0, y - 0.02, f"Kernel extent\n{extent}", color="#ffd24a", fontsize=8, va="top")

    fig.text(
        0.055,
        0.045,
        "Note: rendered from routed Vivado primitive LOC data exported by the AE linkhook. "
        "Dim cells are shell/platform and non-highlighted logic, highlighted cells are the TempGNN hierarchy.",
        color="#7f8da6",
        fontsize=8,
    )
    fig.savefig(out_png, dpi=170, facecolor=fig.get_facecolor())
    fig.savefig(out_svg, facecolor=fig.get_facecolor())
    plt.close(fig)


def render_fallback_layout(summary: dict, out_png: Path, out_svg: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ModuleNotFoundError:
        render_fallback_layout_pil(summary, out_png, out_svg)
        return

    bg = "#070b16"
    fig = plt.figure(figsize=(18, 11), facecolor=bg)
    ax = fig.add_axes([0.07, 0.12, 0.78, 0.75], facecolor=bg)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#8fa6c8")
        spine.set_linewidth(1.3)
    for y, label in [(33.3, "SLR0"), (66.6, "SLR1")]:
        ax.axhline(y, color="#8a6ad8", linewidth=1.2)
    resources = summary.get("resources", {}).get("kernel", {})
    bars = [
        ("LUT", resources.get("lut_pct")),
        ("FF", resources.get("ff_pct")),
        ("BRAM", resources.get("bram_pct")),
        ("URAM", resources.get("uram_pct")),
        ("DSP", resources.get("dsp_pct")),
    ]
    x = 12
    for label, pct in bars:
        height = 65 * (float(pct or 0) / 100)
        ax.add_patch(Rectangle((x, 15), 9, height, color="#ffd24a", alpha=0.85))
        ax.text(x + 4.5, 10, label, color="#d7dfef", ha="center", fontsize=10)
        ax.text(x + 4.5, 17 + height, f"{float(pct or 0):.2f}%", color="#ffd24a", ha="center", fontsize=9)
        x += 14
    timing = summary.get("post_route_timing", {})
    fig.text(0.07, 0.94, "TempGNN on Alveo U280: routed report-derived FPGA layout", color="#e9eef8", fontsize=20, weight="bold")
    fig.text(0.07, 0.915, f"No routed LOC CSV found, showing routed utilization summary. WNS {format_ns(timing.get('wns_ns'))}", color="#9fb0c9", fontsize=11)
    fig.text(0.07, 0.045, "Run the U280 layout linkhook to export cell LOC data for the full placement scatter plot.", color="#7f8da6", fontsize=8)
    fig.savefig(out_png, dpi=170, facecolor=fig.get_facecolor())
    fig.savefig(out_svg, facecolor=fig.get_facecolor())
    plt.close(fig)


def render_loc_layout_pil(cells: list[dict], summary: dict, out_png: Path, out_svg: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 3200, 2100
    bg = "#070b16"
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    fonts = load_fonts()
    colors = {
        "logic": "#46647f",
        "bram": "#5ea3bb",
        "uram": "#8d66c4",
        "dsp": "#d48a32",
        "shell": "#263246",
        "other": "#33435d",
    }
    kernel_color = "#ffd24a"
    kernel_edge = "#ff8c42"

    left, top, right, bottom = 140, 230, 2620, 1830
    xs = [c["x"] for c in cells]
    ys = [c["y"] for c in cells]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    dx = max(1, max_x - min_x)
    dy = max(1, max_y - min_y)

    def map_xy(cell: dict) -> tuple[int, int]:
        x = left + int((cell["x"] - min_x) / dx * (right - left))
        y = bottom - int((cell["y"] - min_y) / dy * (bottom - top))
        return x, y

    draw.rectangle((left, top, right, bottom), outline="#8fa6c8", width=3)
    for i in range(1, 8):
        x = left + (right - left) * i // 8
        draw.line((x, top, x, bottom), fill="#283349", width=1)
    for frac, label in [(1 / 3, "SLR0"), (2 / 3, "SLR1")]:
        y = bottom - int((bottom - top) * frac)
        draw.line((left, y, right, y), fill="#8a6ad8", width=3)
    for frac, label in [(1 / 6, "SLR0"), (3 / 6, "SLR1"), (5 / 6, "SLR2")]:
        y = bottom - int((bottom - top) * frac)
        draw.text((45, y - 14), label, fill="#9b83e6", font=fonts["small"])

    for cell in cells:
        if cell["is_kernel"]:
            continue
        x, y = map_xy(cell)
        draw.point((x, y), fill=colors.get(cell["kind"], colors["other"]))

    kernel = [c for c in cells if c["is_kernel"]]
    for cell in kernel:
        x, y = map_xy(cell)
        draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=kernel_color)

    if kernel:
        kpts = [map_xy(c) for c in kernel]
        kmin_x, kmax_x = min(p[0] for p in kpts), max(p[0] for p in kpts)
        kmin_y, kmax_y = min(p[1] for p in kpts), max(p[1] for p in kpts)
        draw.rectangle((kmin_x - 8, kmin_y - 8, kmax_x + 8, kmax_y + 8), outline=kernel_edge, width=4)
        extent = f"x={min(c['x'] for c in kernel)}-{max(c['x'] for c in kernel)}, y={min(c['y'] for c in kernel)}-{max(c['y'] for c in kernel)}"
    else:
        extent = "kernel hierarchy not tagged in LOC CSV"

    timing = summary.get("post_route_timing", {})
    title = summary.get("layout_title", "TempGNN on Alveo U280: real post-route FPGA placement")
    subtitle = (
        f"{summary.get('platform_vbnv', 'xilinx_u280')} routed build, "
        f"WNS {format_ns(timing.get('wns_ns'))}, "
        f"{len(cells):,} placed primitives exported from Vivado LOC"
    )
    draw.text((70, 60), title, fill="#e9eef8", font=fonts["title"])
    draw.text((72, 112), subtitle, fill="#9fb0c9", font=fonts["body"])

    lx, ly = 2700, 280
    draw.text((lx, ly), "Post-route evidence", fill="#e9eef8", font=fonts["body_bold"])
    ly += 54
    for text in [
        f"Device  {summary.get('device', 'xcu280')}",
        f"Shell   {summary.get('shell', summary.get('platform_vbnv', 'U280'))}",
        f"Timing  WNS {format_ns(timing.get('wns_ns'))}",
        f"Kernel cells  {len(kernel):,}",
    ]:
        draw.text((lx, ly), text, fill="#b9c5d9", font=fonts["small"])
        ly += 38
    ly += 25
    draw.text((lx, ly), "Primitive classes", fill="#e9eef8", font=fonts["body_bold"])
    ly += 48
    for label, color in [
        ("U280 shell/other cells", colors["shell"]),
        ("U280 LUT/FF/register", colors["logic"]),
        ("U280 BRAM", colors["bram"]),
        ("U280 URAM", colors["uram"]),
        ("U280 DSP", colors["dsp"]),
        ("TempGNN kernel cells", kernel_color),
    ]:
        draw.rectangle((lx, ly - 10, lx + 38, ly + 14), fill=color)
        draw.text((lx + 55, ly - 13), label, fill="#cbd6e6", font=fonts["small"])
        ly += 43
    ly += 25
    draw.text((lx, ly), "Kernel extent", fill="#ffd24a", font=fonts["small"])
    draw.text((lx, ly + 32), extent, fill="#ffd24a", font=fonts["small"])

    draw.text(
        (70, 1990),
        "Note: rendered from routed Vivado primitive LOC data exported by the AE linkhook. "
        "Dim cells are shell/platform and non-highlighted logic, highlighted cells are the TempGNN hierarchy.",
        fill="#7f8da6",
        font=fonts["small"],
    )

    image.save(out_png)
    write_loc_svg(cells, summary, out_svg, min_x, max_x, min_y, max_y)


def render_fallback_layout_pil(summary: dict, out_png: Path, out_svg: Path) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (2400, 1400), "#070b16")
    draw = ImageDraw.Draw(image)
    fonts = load_fonts()
    draw.text((80, 70), "TempGNN on Alveo U280: routed report-derived FPGA layout", fill="#e9eef8", font=fonts["title"])
    timing = summary.get("post_route_timing", {})
    draw.text((82, 128), f"No routed LOC CSV found. WNS {format_ns(timing.get('wns_ns'))}", fill="#9fb0c9", font=fonts["body"])
    left, top, right, bottom = 120, 220, 2050, 1150
    draw.rectangle((left, top, right, bottom), outline="#8fa6c8", width=3)
    resources = summary.get("resources", {}).get("kernel", {})
    bars = [
        ("LUT", resources.get("lut_pct")),
        ("FF", resources.get("ff_pct")),
        ("BRAM", resources.get("bram_pct")),
        ("URAM", resources.get("uram_pct")),
        ("DSP", resources.get("dsp_pct")),
    ]
    x = 220
    for label, pct in bars:
        pct = float(pct or 0)
        h = int(720 * pct / 100)
        draw.rectangle((x, bottom - h, x + 150, bottom), fill="#ffd24a")
        draw.text((x + 45, bottom + 30), label, fill="#d7dfef", font=fonts["small"])
        draw.text((x + 25, bottom - h - 42), f"{pct:.2f}%", fill="#ffd24a", font=fonts["small"])
        x += 250
    image.save(out_png)
    write_simple_svg(out_svg, "TempGNN U280 routed report-derived layout", "No routed LOC CSV found")


def load_fonts() -> dict:
    from PIL import ImageFont

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    regular = next((p for p in candidates if Path(p).exists() and "Bold" not in p and "arialbd" not in p), None)
    bold = next((p for p in candidates if Path(p).exists() and ("Bold" in p or "arialbd" in p)), regular)

    def font(path: str | None, size: int):
        if path:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
        return ImageFont.load_default()

    return {
        "title": font(bold, 42),
        "body_bold": font(bold, 24),
        "body": font(regular, 24),
        "small": font(regular, 20),
    }


def write_loc_svg(cells: list[dict], summary: dict, out_svg: Path, min_x: int, max_x: int, min_y: int, max_y: int) -> None:
    width, height = 1600, 1050
    left, top, right, bottom = 70, 115, 1310, 915
    dx = max(1, max_x - min_x)
    dy = max(1, max_y - min_y)
    colors = {
        "logic": "#46647f",
        "bram": "#5ea3bb",
        "uram": "#8d66c4",
        "dsp": "#d48a32",
        "shell": "#263246",
        "other": "#33435d",
    }

    def map_xy(cell: dict) -> tuple[int, int]:
        x = left + int((cell["x"] - min_x) / dx * (right - left))
        y = bottom - int((cell["y"] - min_y) / dy * (bottom - top))
        return x, y

    sample_step = max(1, len(cells) // 60000)
    rects = []
    for i, cell in enumerate(cells):
        if i % sample_step:
            continue
        x, y = map_xy(cell)
        color = "#ffd24a" if cell["is_kernel"] else colors.get(cell["kind"], colors["other"])
        rects.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{color}" />')
    timing = summary.get("post_route_timing", {})
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#070b16" />',
        '<text x="70" y="48" fill="#e9eef8" font-size="28" font-family="Arial" font-weight="bold">TempGNN on Alveo U280: real post-route FPGA placement</text>',
        f'<text x="70" y="78" fill="#9fb0c9" font-size="14" font-family="Arial">WNS {format_ns(timing.get("wns_ns"))}; SVG sampled from routed LOC CSV for file size</text>',
        f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="none" stroke="#8fa6c8" stroke-width="2" />',
        f'<line x1="{left}" y1="{top+(bottom-top)//3}" x2="{right}" y2="{top+(bottom-top)//3}" stroke="#8a6ad8" stroke-width="2" />',
        f'<line x1="{left}" y1="{top+2*(bottom-top)//3}" x2="{right}" y2="{top+2*(bottom-top)//3}" stroke="#8a6ad8" stroke-width="2" />',
        *rects,
        '<text x="1350" y="170" fill="#e9eef8" font-size="16" font-family="Arial" font-weight="bold">Post-route evidence</text>',
        f'<text x="1350" y="205" fill="#b9c5d9" font-size="12" font-family="Arial">Device {summary.get("device", "xcu280")}</text>',
        f'<text x="1350" y="230" fill="#b9c5d9" font-size="12" font-family="Arial">Timing WNS {format_ns(timing.get("wns_ns"))}</text>',
        '<rect x="1350" y="270" width="18" height="12" fill="#ffd24a" /><text x="1378" y="281" fill="#cbd6e6" font-size="12" font-family="Arial">TempGNN kernel cells</text>',
        '</svg>',
    ]
    out_svg.write_text("\n".join(svg), encoding="utf-8")


def write_simple_svg(out_svg: Path, title: str, subtitle: str) -> None:
    out_svg.write_text(
        "\n".join(
            [
                '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="700">',
                '<rect width="100%" height="100%" fill="#070b16" />',
                f'<text x="60" y="80" fill="#e9eef8" font-size="30" font-family="Arial" font-weight="bold">{title}</text>',
                f'<text x="60" y="120" fill="#9fb0c9" font-size="18" font-family="Arial">{subtitle}</text>',
                '</svg>',
            ]
        ),
        encoding="utf-8",
    )


def format_ns(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "+" if number >= 0 else ""
    return f"{sign}{number:.3f} ns"


if __name__ == "__main__":
    main()
