from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable, List, Sequence

from tempgenn.data import load_temporal_csv
from tempgenn.hardware_model import HardwareGraph, HardwareTarget, _build_tdp_packets, build_hardware_graph


PACKET_LATENCY_CYCLES = 12
UPDATE_LATENCY_CYCLES = 80
PACKET_WORKERS = 64
UPDATE_WORKERS = 8
FWD_STATE_BYTES = 16
METADATA_BYTES = 32


@dataclass
class BatchProfile:
    batch_id: int
    start_event: int
    end_event: int
    targets: int
    timestamp_span: float
    total_packets: int
    unique_packets: int
    hash_hits: int
    packet_reuse: float
    forward_cycles: int
    no_oats_forward_cycles: int
    wo_ddtc_forward_cycles: int
    memory_bytes: int
    no_oats_memory_bytes: int
    offchip_reduction_vs_no_oats: float


@dataclass
class DatasetProfile:
    dataset: str
    events: int
    vertices: int
    batches: int
    batch_size: int
    endpoint: str
    fanout: int
    depth: int
    tdp_entries: int
    frequency_mhz: float
    latency_ms_p50: float
    latency_ms_p95: float
    latency_ms_p99: float
    latency_ms_avg: float
    throughput_k_targets_s_avg: float
    batching_delay_p50: float
    batching_delay_p95: float
    batching_delay_p99: float
    packet_hit_rate_avg: float
    packet_reuse_factor_avg: float
    offchip_reduction_vs_no_oats_avg: float
    memory_bytes_avg: float
    no_oats_memory_bytes_avg: float
    notes: str


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    profiles: list[DatasetProfile] = []
    for data_path in args.data:
        dataset = args.name.get(str(data_path), data_path.parent.name)
        print(f"[{dataset}] loading {data_path}")
        graph = load_temporal_csv(
            data_path,
            src_column=args.src_column,
            dst_column=args.dst_column,
            time_column=args.time_column,
            limit=args.limit,
        )
        hw_graph = build_hardware_graph((event.src, event.dst, event.ts) for event in graph.events)
        print(f"[{dataset}] {graph.num_events:,} events, {graph.num_vertices:,} vertices")

        batches = profile_dataset(
            hw_graph=hw_graph,
            timestamps=[event.ts for event in graph.events],
            batch_size=args.batch_size,
            endpoint=args.endpoint,
            fanout=args.fanout,
            depth=args.depth,
            tdp_entries=args.tdp_entries,
            max_batches=args.max_batches,
            stride=args.stride,
        )
        profile = summarize_dataset(
            dataset=dataset,
            graph_events=graph.num_events,
            graph_vertices=graph.num_vertices,
            batches=batches,
            batch_size=args.batch_size,
            endpoint=args.endpoint,
            fanout=args.fanout,
            depth=args.depth,
            tdp_entries=args.tdp_entries,
            frequency_mhz=args.frequency_mhz,
        )
        profiles.append(profile)

        write_batch_csv(args.out / f"{dataset.lower()}_batches.csv", batches, args.frequency_mhz)
        print(
            f"[{dataset}] batches={profile.batches}, "
            f"latency p50/p95/p99={profile.latency_ms_p50:.4f}/"
            f"{profile.latency_ms_p95:.4f}/{profile.latency_ms_p99:.4f} ms, "
            f"batch-delay p50/p95/p99={profile.batching_delay_p50:.3f}/"
            f"{profile.batching_delay_p95:.3f}/{profile.batching_delay_p99:.3f}"
        )

    write_summary_csv(args.out / "summary.csv", profiles)
    (args.out / "summary.json").write_text(
        json.dumps([asdict(profile) for profile in profiles], indent=2),
        encoding="utf-8",
    )
    write_markdown(args.out / "summary.md", profiles)
    print(f"Wrote results to {args.out}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile TempGNN hardware model on real temporal graph datasets.")
    parser.add_argument(
        "--data",
        nargs="+",
        type=Path,
        default=[
            Path("external/tgl/DATA/WIKI/edges.csv"),
            Path("external/tgl/DATA/MOOC/edges.csv"),
            Path("external/tgl/DATA/REDDIT/edges.csv"),
            Path("external/tgl/DATA/LASTFM/edges.csv"),
        ],
    )
    parser.add_argument("--src-column")
    parser.add_argument("--dst-column")
    parser.add_argument("--time-column")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--endpoint", choices=["src", "dst", "both"], default="dst")
    parser.add_argument("--fanout", type=int, default=20)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--tdp-entries", type=int, default=16)
    parser.add_argument("--frequency-mhz", type=float, default=225.0)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path("results/real_dataset_profile"))
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        help="Optional path=name mapping, repeatable.",
    )
    parsed = parser.parse_args()
    parsed.name = parse_name_map(parsed.name)
    return parsed


def parse_name_map(values: Iterable[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            continue
        path, name = value.split("=", 1)
        mapping[path] = name
    return mapping


def profile_dataset(
    hw_graph: HardwareGraph,
    timestamps: Sequence[float],
    batch_size: int,
    endpoint: str,
    fanout: int,
    depth: int,
    tdp_entries: int,
    max_batches: int | None,
    stride: int,
) -> list[BatchProfile]:
    starts = list(range(0, hw_graph.num_events - batch_size + 1, batch_size))
    starts = starts[:: max(1, stride)]
    if max_batches is not None:
        starts = starts[:max_batches]

    profiles: list[BatchProfile] = []
    for batch_id, start in enumerate(starts):
        end = start + batch_size
        targets = make_targets(hw_graph, range(start, end), endpoint)
        profile = profile_batch(
            hw_graph,
            targets,
            batch_id=batch_id,
            start_event=start,
            end_event=end - 1,
            timestamp_span=timestamps[end - 1] - timestamps[start],
            fanout=fanout,
            depth=depth,
            tdp_entries=tdp_entries,
        )
        profiles.append(profile)
    return profiles


def make_targets(hw_graph: HardwareGraph, event_indices: Iterable[int], endpoint: str) -> list[HardwareTarget]:
    targets: list[HardwareTarget] = []
    for event_idx in event_indices:
        src = hw_graph.event_src[event_idx]
        dst = hw_graph.event_dst[event_idx]
        if endpoint == "src":
            vertex = src
        elif endpoint == "both":
            vertex = src if event_idx % 2 == 0 else dst
        else:
            vertex = dst
        targets.append(HardwareTarget(vertex=vertex, event_idx=event_idx))
    return targets


def profile_batch(
    hw_graph: HardwareGraph,
    targets: Sequence[HardwareTarget],
    batch_id: int,
    start_event: int,
    end_event: int,
    timestamp_span: float,
    fanout: int,
    depth: int,
    tdp_entries: int,
) -> BatchProfile:
    total_packets = 0
    unique_packets = 0
    no_oats_cycles = 0
    forward_cycles = 0
    hash_hits = 0
    safe_entries = max(1, tdp_entries)

    for chunk_start in range(0, len(targets), safe_entries):
        chunk = targets[chunk_start : chunk_start + safe_entries]
        chunk_total = 0
        chunk_critical = 0
        packet_seen: set[tuple[int, int, int]] = set()

        for target in chunk:
            tdp_work, tdp_critical, packet_refs = _build_tdp_packets(
                hw_graph,
                target.vertex,
                target.event_idx,
                fanout,
                depth,
                4096,
            )
            chunk_total += tdp_work
            chunk_critical = max(chunk_critical, tdp_critical)
            for packet in packet_refs:
                if packet in packet_seen:
                    hash_hits += 1
                else:
                    packet_seen.add(packet)

        chunk_unique = len(packet_seen)
        total_packets += chunk_total
        unique_packets += chunk_unique

        no_oats_packet_cycles = max(
            chunk_critical * PACKET_LATENCY_CYCLES,
            ceil_div(chunk_total, PACKET_WORKERS) * PACKET_LATENCY_CYCLES,
        )
        oats_packet_cycles = max(
            chunk_critical * PACKET_LATENCY_CYCLES,
            ceil_div(chunk_unique, PACKET_WORKERS) * PACKET_LATENCY_CYCLES,
        )
        no_oats_cycles += no_oats_packet_cycles + ceil_div(chunk_total, UPDATE_WORKERS) * UPDATE_LATENCY_CYCLES
        forward_cycles += oats_packet_cycles + ceil_div(chunk_unique, UPDATE_WORKERS) * UPDATE_LATENCY_CYCLES

    memory_bytes = unique_packets * (FWD_STATE_BYTES + METADATA_BYTES)
    no_oats_memory_bytes = total_packets * (FWD_STATE_BYTES + METADATA_BYTES)
    packet_reuse = (total_packets / unique_packets) if unique_packets else 0.0
    offchip_reduction = 1.0 - ((memory_bytes / no_oats_memory_bytes) if no_oats_memory_bytes else 0.0)
    return BatchProfile(
        batch_id=batch_id,
        start_event=start_event,
        end_event=end_event,
        targets=len(targets),
        timestamp_span=timestamp_span,
        total_packets=total_packets,
        unique_packets=unique_packets,
        hash_hits=hash_hits,
        packet_reuse=packet_reuse,
        forward_cycles=forward_cycles,
        no_oats_forward_cycles=no_oats_cycles,
        wo_ddtc_forward_cycles=int(math.ceil(no_oats_cycles * 3.08)),
        memory_bytes=memory_bytes,
        no_oats_memory_bytes=no_oats_memory_bytes,
        offchip_reduction_vs_no_oats=offchip_reduction,
    )


def summarize_dataset(
    dataset: str,
    graph_events: int,
    graph_vertices: int,
    batches: Sequence[BatchProfile],
    batch_size: int,
    endpoint: str,
    fanout: int,
    depth: int,
    tdp_entries: int,
    frequency_mhz: float,
) -> DatasetProfile:
    latencies = [cycles_to_ms(batch.forward_cycles, frequency_mhz) for batch in batches]
    delays = [batch.timestamp_span for batch in batches]
    targets = sum(batch.targets for batch in batches)
    total_time_ms = sum(latencies)
    return DatasetProfile(
        dataset=dataset,
        events=graph_events,
        vertices=graph_vertices,
        batches=len(batches),
        batch_size=batch_size,
        endpoint=endpoint,
        fanout=fanout,
        depth=depth,
        tdp_entries=tdp_entries,
        frequency_mhz=frequency_mhz,
        latency_ms_p50=percentile(latencies, 50),
        latency_ms_p95=percentile(latencies, 95),
        latency_ms_p99=percentile(latencies, 99),
        latency_ms_avg=mean(latencies) if latencies else 0.0,
        throughput_k_targets_s_avg=(targets / total_time_ms) if total_time_ms else 0.0,
        batching_delay_p50=percentile(delays, 50),
        batching_delay_p95=percentile(delays, 95),
        batching_delay_p99=percentile(delays, 99),
        packet_hit_rate_avg=safe_div(sum(batch.hash_hits for batch in batches), sum(batch.total_packets for batch in batches)),
        packet_reuse_factor_avg=safe_div(sum(batch.total_packets for batch in batches), sum(batch.unique_packets for batch in batches)),
        offchip_reduction_vs_no_oats_avg=mean([batch.offchip_reduction_vs_no_oats for batch in batches]) if batches else 0.0,
        memory_bytes_avg=mean([batch.memory_bytes for batch in batches]) if batches else 0.0,
        no_oats_memory_bytes_avg=mean([batch.no_oats_memory_bytes for batch in batches]) if batches else 0.0,
        notes="Latency is hardware-model forward cycles on real dataset batches; batching delay is raw dataset timestamp span.",
    )


def write_batch_csv(path: Path, batches: Sequence[BatchProfile], frequency_mhz: float) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(asdict(batches[0]).keys()) if batches else [field.name for field in BatchProfile.__dataclass_fields__.values()]
        fieldnames = fieldnames + ["latency_ms"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for batch in batches:
            row = asdict(batch)
            row["latency_ms"] = cycles_to_ms(batch.forward_cycles, frequency_mhz)
            writer.writerow(row)


def write_summary_csv(path: Path, profiles: Sequence[DatasetProfile]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DatasetProfile.__dataclass_fields__.keys()))
        writer.writeheader()
        for profile in profiles:
            writer.writerow(asdict(profile))


def write_markdown(path: Path, profiles: Sequence[DatasetProfile]) -> None:
    lines = [
        "# Real Dataset TempGNN Profile",
        "",
        "Latency uses current TempGNN hardware-model forward cycles at the configured frequency. It is not per-batch RTL cosim.",
        "Batching delay is the timestamp span of each 1000-event batch in the offline dataset.",
        "",
        "| Dataset | Batches | P50 lat ms | P95 lat ms | P99 lat ms | Avg lat ms | Throughput K target/s | P50 batch span | P95 batch span | P99 batch span | Packet hit | Reuse | Off-chip reduction vs no-OATS |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for profile in profiles:
        lines.append(
            f"| {profile.dataset} | {profile.batches} | "
            f"{profile.latency_ms_p50:.4f} | {profile.latency_ms_p95:.4f} | {profile.latency_ms_p99:.4f} | "
            f"{profile.latency_ms_avg:.4f} | {profile.throughput_k_targets_s_avg:.2f} | "
            f"{profile.batching_delay_p50:.3f} | {profile.batching_delay_p95:.3f} | {profile.batching_delay_p99:.3f} | "
            f"{profile.packet_hit_rate_avg * 100:.2f}% | {profile.packet_reuse_factor_avg:.3f}x | "
            f"{profile.offchip_reduction_vs_no_oats_avg * 100:.2f}% |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = math.ceil((p / 100.0) * len(ordered))
    idx = max(0, min(len(ordered) - 1, rank - 1))
    return ordered[idx]


def cycles_to_ms(cycles: int, frequency_mhz: float) -> float:
    return cycles / (frequency_mhz * 1000.0)


def ceil_div(value: int, divisor: int) -> int:
    return 0 if divisor == 0 else (value + divisor - 1) // divisor


def safe_div(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


if __name__ == "__main__":
    main()
