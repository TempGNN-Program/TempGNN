from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Iterable, List

from tempgenn.data import load_temporal_csv
from tempgenn.functional import TinyTGNNStateModel
from tempgenn.graph import TemporalGraph
from tempgenn.simulator import BatchMetrics, SimulationConfig, simulate_batch
from tempgenn.synthetic import generate_synthetic_graph
from tempgenn.tdp import TDPBuilder


def main() -> None:
    args = parse_args()
    graph = build_graph(args)
    targets = graph.targets_from_recent_events(args.batch_size, endpoint=args.target_endpoint)
    config = SimulationConfig(
        fanout=args.fanout,
        depth=args.depth,
        tdp_entries=args.tdp_entries,
        packet_workers=args.packet_workers,
        update_workers=args.update_workers,
        frequency_mhz=args.frequency_mhz,
    )

    metrics = simulate_batch(graph, targets, config)
    print_summary(graph, metrics)

    if args.verify_functional:
        builder = TDPBuilder(graph, fanout=min(args.fanout, 8), depth=args.depth)
        check_tdps = builder.build_many(targets[: min(len(targets), 64)])
        result = TinyTGNNStateModel(graph).verify_tdps(check_tdps)
        print()
        print("Functional packet check")
        print(f"  packets_checked: {result.packets_checked}")
        print(f"  max_abs_error:   {result.max_abs_error:.3e}")
        print(f"  passed:          {result.passed}")

    if args.sensitivity:
        print()
        print("Batch-size sensitivity")
        print_sensitivity(
            graph,
            config,
            values=[400, 600, 800, 1000, 1200],
            field="batch_size",
        )
        print()
        print("TDP-entry sensitivity")
        print_sensitivity(
            graph,
            config,
            values=[2, 4, 6, 8, 16, 32, 64],
            field="tdp_entries",
            fixed_batch_size=args.batch_size,
        )

    if args.out:
        Path(args.out).write_text(metrics.to_json() + "\n", encoding="utf-8")
        print()
        print(f"Wrote metrics to {args.out}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Board-free TempGNN reproduction")
    parser.add_argument("--data", help="Optional temporal graph CSV")
    parser.add_argument("--src-column")
    parser.add_argument("--dst-column")
    parser.add_argument("--time-column")
    parser.add_argument("--limit", type=int, help="Limit CSV rows")
    parser.add_argument("--vertices", type=int, default=5000)
    parser.add_argument("--edges", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--target-endpoint", choices=("src", "dst", "both"), default="dst")
    parser.add_argument("--fanout", type=int, default=20)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--tdp-entries", type=int, default=16)
    parser.add_argument("--packet-workers", type=int, default=64)
    parser.add_argument("--update-workers", type=int, default=8)
    parser.add_argument("--frequency-mhz", type=float, default=225.0)
    parser.add_argument("--verify-functional", action="store_true")
    parser.add_argument("--sensitivity", action="store_true")
    parser.add_argument("--out", help="Write primary metrics JSON")
    return parser.parse_args()


def build_graph(args: argparse.Namespace) -> TemporalGraph:
    if args.data:
        return load_temporal_csv(
            args.data,
            src_column=args.src_column,
            dst_column=args.dst_column,
            time_column=args.time_column,
            limit=args.limit,
        )
    return generate_synthetic_graph(vertices=args.vertices, edges=args.edges, seed=args.seed)


def print_summary(graph: TemporalGraph, metrics: BatchMetrics) -> None:
    print("TempGNN board-free reproduction")
    print(f"  graph:   {graph.num_vertices:,} vertices, {graph.num_events:,} events")
    print(f"  targets: {metrics.targets:,}, fanout={metrics.fanout}, depth={metrics.depth}")
    print()
    rows = [
        ("total_tdp_packets", f"{metrics.total_tdp_packets:,}"),
        ("unique_tdp_packets", f"{metrics.unique_tdp_packets:,}"),
        ("packet_reuse_factor", f"{metrics.packet_reuse_factor:.3f}x"),
        ("avg_packets_per_target", f"{metrics.avg_packets_per_target:.2f}"),
        ("avg_critical_path", f"{metrics.avg_critical_path:.2f}"),
        ("avg_branch_parallelism_ratio", f"{metrics.avg_branch_parallelism_ratio:.3f}"),
        ("top_0.5pct_hot_vertex_access_ratio", f"{metrics.top_hot_vertex_access_ratio:.3f}"),
        ("cascade_proxy_latency_ms", f"{metrics.cascade_proxy_latency_ms:.3f}"),
        ("tempgenn_latency_ms", f"{metrics.tempgenn_latency_ms:.3f}"),
        ("speedup_vs_cascade_proxy", f"{metrics.speedup_vs_cascade_proxy:.2f}x"),
        ("speedup_vs_wo_ddtc", f"{metrics.speedup_vs_wo_ddtc:.2f}x"),
        ("speedup_vs_wo_oats", f"{metrics.speedup_vs_wo_oats:.2f}x"),
        ("memory_reduction_vs_cascade", f"{metrics.memory_reduction_vs_cascade:.3f}"),
    ]
    width = max(len(name) for name, _ in rows)
    for name, value in rows:
        print(f"  {name:<{width}}  {value}")


def print_sensitivity(
    graph: TemporalGraph,
    config: SimulationConfig,
    values: Iterable[int],
    field: str,
    fixed_batch_size: int | None = None,
) -> None:
    print("  value,tempgenn_cycles,speedup_vs_cascade,packet_reuse")
    for value in values:
        if field == "batch_size":
            targets = graph.targets_from_recent_events(value)
            next_config = config
        elif field == "tdp_entries":
            targets = graph.targets_from_recent_events(fixed_batch_size or 1000)
            next_config = replace(config, tdp_entries=value)
        else:
            raise ValueError(field)
        metrics = simulate_batch(graph, targets, next_config)
        print(
            "  "
            f"{value},{metrics.tempgenn_cycles},"
            f"{metrics.speedup_vs_cascade_proxy:.3f},"
            f"{metrics.packet_reuse_factor:.3f}"
        )


if __name__ == "__main__":
    main()
