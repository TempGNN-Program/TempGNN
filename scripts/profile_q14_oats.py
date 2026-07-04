from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tempgenn.data import load_temporal_csv
from tempgenn.hardware_model import (
    HardwareGraph,
    HardwareTarget,
    INITIAL_EVENT,
    Packet,
    _packet_hash,
    build_hardware_graph,
)


PACKET_LATENCY_CYCLES = 12
UPDATE_LATENCY_CYCLES = 80
PACKET_WORKERS = 64
UPDATE_WORKERS = 8
STATE_BYTES = 16
METADATA_BYTES = 32
HASH_BUCKETS = 2048
HASH_WAYS = 4
MAX_DEGREE_SCAN = 4096


DATASET_DEFAULTS = {
    "WIKI": {
        "path": Path("external/tgl/DATA/WIKI/edges.csv"),
        "stride": 1,
        "coverage": "full",
    },
    "MOOC": {
        "path": Path("external/tgl/DATA/MOOC/edges.csv"),
        "stride": 1,
        "coverage": "full",
    },
    "REDDIT": {
        "path": Path("external/tgl/DATA/REDDIT/edges.csv"),
        "stride": 10,
        "coverage": "stride=10",
    },
    "LASTFM": {
        "path": Path("external/tgl/DATA/LASTFM/edges.csv"),
        "stride": 20,
        "coverage": "stride=20",
    },
}


MODEL_PROFILES = {
    # These are dependency-scope profiles for the current HLS kernel, not trained
    # model checkpoints. They make the model dimension explicit and reproducible.
    "JODIE": {"fanout": 0, "depth": 0, "endpoint": "dst"},
    "TGAT": {"fanout": 10, "depth": 1, "endpoint": "dst"},
    "TGN": {"fanout": 20, "depth": 2, "endpoint": "dst"},
    "APAN": {"fanout": 20, "depth": 2, "endpoint": "dst"},
}


@dataclass
class ChunkCounters:
    total_packets: int = 0
    memory_packets: int = 0
    hash_hits: int = 0
    insert_attempts: int = 0
    colliding_inserts: int = 0
    collision_probes: int = 0
    full_bucket_fallbacks: int = 0
    critical_path_packets: int = 0
    sync_stall_cycles: int = 0
    forward_cycles: int = 0
    no_oats_cycles: int = 0


@dataclass
class BatchCounters:
    dataset: str
    model: str
    coverage: str
    batch_id: int
    start_event: int
    end_event: int
    targets: int
    timestamp_span: float
    endpoint: str
    fanout: int
    depth: int
    tdp_entries: int
    total_packets: int
    memory_packets: int
    hash_hits: int
    insert_attempts: int
    colliding_inserts: int
    collision_probes: int
    full_bucket_fallbacks: int
    sync_stall_cycles: int
    forward_cycles: int
    no_oats_cycles: int
    memory_bytes: int
    no_oats_memory_bytes: int


@dataclass
class SummaryCounters:
    dataset: str
    model: str
    coverage: str
    events: int
    vertices: int
    batches: int
    batch_size: int
    endpoint: str
    fanout: int
    depth: int
    tdp_entries: int
    frequency_mhz: float
    total_packets: int
    memory_packets: int
    hash_hits: int
    packet_hit_rate: float
    packet_reuse_rate: float
    packet_reuse_factor: float
    hash_collision_insert_rate: float
    full_bucket_fallback_rate: float
    collision_probe_per_insert: float
    sync_stall_rate: float
    sync_stall_cycles_per_batch: float
    offchip_reduction_vs_no_sharing: float
    latency_ms_avg: float
    latency_ms_p50: float
    latency_ms_p95: float
    latency_ms_p99: float
    batching_span_p50: float
    batching_span_p95: float
    batching_span_p99: float
    notes: str


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    dataset_names = args.datasets or list(DATASET_DEFAULTS)
    model_names = args.models or list(MODEL_PROFILES)

    all_batches: list[BatchCounters] = []
    summaries: list[SummaryCounters] = []
    for dataset_name in dataset_names:
        if dataset_name not in DATASET_DEFAULTS:
            raise ValueError(f"Unknown dataset {dataset_name}. Choices: {', '.join(DATASET_DEFAULTS)}")
        dataset_cfg = DATASET_DEFAULTS[dataset_name]
        stride = 1 if args.full_all else int(dataset_cfg["stride"])
        coverage = "full" if stride == 1 else f"stride={stride}"
        path = Path(dataset_cfg["path"])
        print(f"[{dataset_name}] loading {path}", flush=True)
        graph = load_temporal_csv(path, limit=args.limit)
        hw_graph = build_hardware_graph((event.src, event.dst, event.ts) for event in graph.events)
        timestamps = [event.ts for event in graph.events]
        print(f"[{dataset_name}] events={graph.num_events:,}, vertices={graph.num_vertices:,}, coverage={coverage}", flush=True)

        profile_cache: dict[tuple[str, int, int, int, int, int | None, int | None], list[BatchCounters]] = {}
        for model_name in model_names:
            if model_name not in MODEL_PROFILES:
                raise ValueError(f"Unknown model {model_name}. Choices: {', '.join(MODEL_PROFILES)}")
            model_cfg = MODEL_PROFILES[model_name]
            print(
                f"[{dataset_name}/{model_name}] fanout={model_cfg['fanout']} "
                f"depth={model_cfg['depth']} endpoint={model_cfg['endpoint']}",
                flush=True,
            )
            cache_key = (
                str(model_cfg["endpoint"]),
                int(model_cfg["fanout"]),
                int(model_cfg["depth"]),
                args.tdp_entries,
                stride,
                args.max_batches,
                args.sample_batches,
            )
            if cache_key in profile_cache:
                batches = [replace(batch, model=model_name) for batch in profile_cache[cache_key]]
                print(f"[{dataset_name}/{model_name}] reused cached dependency profile", flush=True)
            else:
                batches = profile_dataset_model(
                    dataset=dataset_name,
                    model=model_name,
                    coverage=coverage,
                    hw_graph=hw_graph,
                    timestamps=timestamps,
                    batch_size=args.batch_size,
                    endpoint=str(model_cfg["endpoint"]),
                    fanout=int(model_cfg["fanout"]),
                    depth=int(model_cfg["depth"]),
                    tdp_entries=args.tdp_entries,
                    stride=stride,
                    max_batches=args.max_batches,
                    sample_batches=args.sample_batches,
                )
                profile_cache[cache_key] = batches
            all_batches.extend(batches)
            summary = summarize(
                dataset=dataset_name,
                model=model_name,
                coverage=coverage,
                events=graph.num_events,
                vertices=graph.num_vertices,
                batch_size=args.batch_size,
                batches=batches,
                frequency_mhz=args.frequency_mhz,
            )
            summaries.append(summary)
            print(
                f"[{dataset_name}/{model_name}] batches={summary.batches}, "
                f"hit={summary.packet_hit_rate * 100:.2f}%, "
                f"reuse={summary.packet_reuse_rate * 100:.2f}%, "
                f"collision={summary.hash_collision_insert_rate * 100:.3f}%, "
                f"full-bucket={summary.full_bucket_fallback_rate * 100:.4f}%, "
                f"stall={summary.sync_stall_rate * 100:.2f}%, "
                f"mem-reduction={summary.offchip_reduction_vs_no_sharing * 100:.2f}%",
                flush=True,
            )

    write_csv(args.out / "q14_batches.csv", all_batches, BatchCounters)
    write_csv(args.out / "q14_dataset_model_summary.csv", summaries, SummaryCounters)
    write_csv(args.out / "q14_dataset_summary.csv", aggregate_summaries(summaries, "dataset"), SummaryCounters)
    write_csv(args.out / "q14_model_summary.csv", aggregate_summaries(summaries, "model"), SummaryCounters)
    (args.out / "q14_dataset_model_summary.json").write_text(
        json.dumps([asdict(item) for item in summaries], indent=2),
        encoding="utf-8",
    )
    write_markdown(args.out / "q14_summary.md", summaries)
    print(f"Wrote Q14 results to {args.out}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile TempGNN Q14 OATS counters on real TGL datasets.")
    parser.add_argument("--datasets", nargs="+", choices=list(DATASET_DEFAULTS))
    parser.add_argument("--models", nargs="+", choices=list(MODEL_PROFILES))
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--tdp-entries", type=int, default=16)
    parser.add_argument("--frequency-mhz", type=float, default=225.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--sample-batches", type=int)
    parser.add_argument("--full-all", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("results/q14_oats_profile"))
    return parser.parse_args()


def profile_dataset_model(
    dataset: str,
    model: str,
    coverage: str,
    hw_graph: HardwareGraph,
    timestamps: Sequence[float],
    batch_size: int,
    endpoint: str,
    fanout: int,
    depth: int,
    tdp_entries: int,
    stride: int,
    max_batches: int | None,
    sample_batches: int | None,
) -> list[BatchCounters]:
    starts = list(range(0, hw_graph.num_events - batch_size + 1, batch_size))
    starts = starts[:: max(1, stride)]
    if sample_batches is not None and sample_batches > 0 and len(starts) > sample_batches:
        starts = evenly_sample(starts, sample_batches)
    if max_batches is not None:
        starts = starts[:max_batches]

    batches: list[BatchCounters] = []
    for batch_id, start in enumerate(starts):
        end = start + batch_size
        targets = make_targets(hw_graph, range(start, end), endpoint)
        counters = profile_batch(
            targets=targets,
            hw_graph=hw_graph,
            fanout=fanout,
            depth=depth,
            tdp_entries=tdp_entries,
        )
        total_packets = counters.total_packets
        memory_packets = counters.memory_packets
        batches.append(
            BatchCounters(
                dataset=dataset,
                model=model,
                coverage=coverage,
                batch_id=batch_id,
                start_event=start,
                end_event=end - 1,
                targets=len(targets),
                timestamp_span=timestamps[end - 1] - timestamps[start],
                endpoint=endpoint,
                fanout=fanout,
                depth=depth,
                tdp_entries=tdp_entries,
                total_packets=total_packets,
                memory_packets=memory_packets,
                hash_hits=counters.hash_hits,
                insert_attempts=counters.insert_attempts,
                colliding_inserts=counters.colliding_inserts,
                collision_probes=counters.collision_probes,
                full_bucket_fallbacks=counters.full_bucket_fallbacks,
                sync_stall_cycles=counters.sync_stall_cycles,
                forward_cycles=counters.forward_cycles,
                no_oats_cycles=counters.no_oats_cycles,
                memory_bytes=memory_packets * (STATE_BYTES + METADATA_BYTES),
                no_oats_memory_bytes=total_packets * (STATE_BYTES + METADATA_BYTES),
            )
        )
    return batches


def evenly_sample(values: Sequence[int], count: int) -> list[int]:
    if count <= 0:
        return []
    if count >= len(values):
        return list(values)
    if count == 1:
        return [values[0]]
    last = len(values) - 1
    indices = sorted({round(idx * last / (count - 1)) for idx in range(count)})
    return [values[idx] for idx in indices]


def make_targets(hw_graph: HardwareGraph, event_indices: Iterable[int], endpoint: str) -> list[HardwareTarget]:
    targets: list[HardwareTarget] = []
    for event_idx in event_indices:
        src = hw_graph.event_src[event_idx]
        dst = hw_graph.event_dst[event_idx]
        if endpoint == "src":
            targets.append(HardwareTarget(src, event_idx))
        elif endpoint == "both":
            targets.append(HardwareTarget(src if event_idx % 2 == 0 else dst, event_idx))
        elif endpoint == "src_dst":
            targets.append(HardwareTarget(src, event_idx))
            targets.append(HardwareTarget(dst, event_idx))
        else:
            targets.append(HardwareTarget(dst, event_idx))
    return targets


def profile_batch(
    targets: Sequence[HardwareTarget],
    hw_graph: HardwareGraph,
    fanout: int,
    depth: int,
    tdp_entries: int,
) -> ChunkCounters:
    total = ChunkCounters()
    safe_entries = max(1, tdp_entries)
    for chunk_start in range(0, len(targets), safe_entries):
        chunk = targets[chunk_start : chunk_start + safe_entries]
        chunk_packets: list[Packet] = []
        critical_path = 0
        for target in chunk:
            _, tdp_critical, packet_refs = build_tdp_packets_fast(
                hw_graph,
                target.vertex,
                target.event_idx,
                fanout,
                depth,
                MAX_DEGREE_SCAN,
            )
            chunk_packets.extend(packet_refs)
            critical_path = max(critical_path, tdp_critical)

        chunk_counters = simulate_phle_chunk(chunk_packets, critical_path)
        total.total_packets += chunk_counters.total_packets
        total.memory_packets += chunk_counters.memory_packets
        total.hash_hits += chunk_counters.hash_hits
        total.insert_attempts += chunk_counters.insert_attempts
        total.colliding_inserts += chunk_counters.colliding_inserts
        total.collision_probes += chunk_counters.collision_probes
        total.full_bucket_fallbacks += chunk_counters.full_bucket_fallbacks
        total.critical_path_packets = max(total.critical_path_packets, critical_path)
        total.sync_stall_cycles += chunk_counters.sync_stall_cycles
        total.forward_cycles += chunk_counters.forward_cycles
        total.no_oats_cycles += chunk_counters.no_oats_cycles
    return total


def build_tdp_packets_fast(
    graph: HardwareGraph,
    target: int,
    target_idx: int,
    fanout: int,
    depth: int,
    max_degree_scan: int,
) -> tuple[int, int, list[Packet]]:
    queue: list[tuple[Packet, int, int]] = [
        (latest_state_event_fast(graph, target, target_idx + 1, max_degree_scan), depth, 1)
    ]

    if 0 <= target < graph.num_vertices and fanout > 0:
        begin = graph.vertex_offsets[target]
        end = graph.vertex_offsets[target + 1]
        scan_begin = max(begin, end - max_degree_scan)
        pos = bisect_right(graph.history_event_idx, target_idx, scan_begin, end)
        found_neighbors = 0
        while pos > scan_begin and found_neighbors < fanout:
            pos -= 1
            event_idx = graph.history_event_idx[pos]
            peer = graph.history_peer[pos]
            queue.append((latest_state_event_fast(graph, peer, event_idx, max_degree_scan), depth, 1))
            found_neighbors += 1

    seen: set[Packet] = set()
    ordered_packets: list[Packet] = []
    tdp_critical = 0
    head = 0
    while head < len(queue):
        packet, depth_left, depth_from_root = queue[head]
        head += 1
        if packet[1] == INITIAL_EVENT or packet in seen:
            continue
        seen.add(packet)
        ordered_packets.append(packet)
        tdp_critical = max(tdp_critical, depth_from_root)

        if depth_left == 0:
            continue
        event_idx = packet[1]
        src = graph.event_src[event_idx]
        dst = graph.event_dst[event_idx]
        peer = dst if src == packet[0] else src
        queue.append(
            (
                latest_state_event_fast(graph, packet[0], event_idx, max_degree_scan),
                depth_left - 1,
                depth_from_root + 1,
            )
        )
        queue.append(
            (
                latest_state_event_fast(graph, peer, event_idx, max_degree_scan),
                depth_left - 1,
                depth_from_root + 1,
            )
        )

    return len(ordered_packets), tdp_critical, ordered_packets


def latest_state_event_fast(
    graph: HardwareGraph,
    vertex: int,
    before_event_idx: int,
    max_degree_scan: int,
) -> Packet:
    if vertex < 0 or vertex >= graph.num_vertices:
        return (vertex, INITIAL_EVENT, 0)
    begin = graph.vertex_offsets[vertex]
    end = graph.vertex_offsets[vertex + 1]
    scan_begin = max(begin, end - max_degree_scan)
    pos = bisect_left(graph.history_event_idx, before_event_idx, scan_begin, end)
    if pos > scan_begin:
        event_idx = graph.history_event_idx[pos - 1]
        return (vertex, event_idx, graph.event_ts[event_idx])
    return (vertex, INITIAL_EVENT, 0)


def simulate_phle_chunk(packet_refs: Sequence[Packet], critical_path: int) -> ChunkCounters:
    counters = ChunkCounters(total_packets=len(packet_refs), critical_path_packets=critical_path)
    buckets: dict[int, list[Packet]] = {}
    for packet in packet_refs:
        bucket = _packet_hash(packet) % HASH_BUCKETS
        ways = buckets.setdefault(bucket, [])
        if packet in ways:
            counters.hash_hits += 1
            continue

        counters.insert_attempts += 1
        if ways:
            counters.colliding_inserts += 1
            counters.collision_probes += len(ways)

        counters.memory_packets += 1
        if len(ways) < HASH_WAYS:
            ways.append(packet)
        else:
            counters.full_bucket_fallbacks += 1

    critical_cycles = critical_path * PACKET_LATENCY_CYCLES
    no_oats_packet_cycles = max(
        critical_cycles,
        ceil_div(counters.total_packets, PACKET_WORKERS) * PACKET_LATENCY_CYCLES,
    )
    oats_parallel_cycles = ceil_div(counters.memory_packets, PACKET_WORKERS) * PACKET_LATENCY_CYCLES
    oats_packet_cycles = max(critical_cycles, oats_parallel_cycles)
    counters.sync_stall_cycles = max(0, critical_cycles - oats_parallel_cycles)
    counters.no_oats_cycles = no_oats_packet_cycles + ceil_div(counters.total_packets, UPDATE_WORKERS) * UPDATE_LATENCY_CYCLES
    counters.forward_cycles = oats_packet_cycles + ceil_div(counters.memory_packets, UPDATE_WORKERS) * UPDATE_LATENCY_CYCLES
    return counters


def summarize(
    dataset: str,
    model: str,
    coverage: str,
    events: int,
    vertices: int,
    batch_size: int,
    batches: Sequence[BatchCounters],
    frequency_mhz: float,
) -> SummaryCounters:
    if not batches:
        return empty_summary(dataset, model, coverage, events, vertices, batch_size, frequency_mhz)
    first = batches[0]
    total_packets = sum(batch.total_packets for batch in batches)
    memory_packets = sum(batch.memory_packets for batch in batches)
    hash_hits = sum(batch.hash_hits for batch in batches)
    insert_attempts = sum(batch.insert_attempts for batch in batches)
    colliding_inserts = sum(batch.colliding_inserts for batch in batches)
    collision_probes = sum(batch.collision_probes for batch in batches)
    full_bucket_fallbacks = sum(batch.full_bucket_fallbacks for batch in batches)
    sync_stall_cycles = sum(batch.sync_stall_cycles for batch in batches)
    forward_cycles = sum(batch.forward_cycles for batch in batches)
    latencies = [cycles_to_ms(batch.forward_cycles, frequency_mhz) for batch in batches]
    spans = [batch.timestamp_span for batch in batches]
    return SummaryCounters(
        dataset=dataset,
        model=model,
        coverage=coverage,
        events=events,
        vertices=vertices,
        batches=len(batches),
        batch_size=batch_size,
        endpoint=first.endpoint,
        fanout=first.fanout,
        depth=first.depth,
        tdp_entries=first.tdp_entries,
        frequency_mhz=frequency_mhz,
        total_packets=total_packets,
        memory_packets=memory_packets,
        hash_hits=hash_hits,
        packet_hit_rate=safe_div(hash_hits, total_packets),
        packet_reuse_rate=1.0 - safe_div(memory_packets, total_packets),
        packet_reuse_factor=safe_div(total_packets, memory_packets),
        hash_collision_insert_rate=safe_div(colliding_inserts, insert_attempts),
        full_bucket_fallback_rate=safe_div(full_bucket_fallbacks, insert_attempts),
        collision_probe_per_insert=safe_div(collision_probes, insert_attempts),
        sync_stall_rate=safe_div(sync_stall_cycles, forward_cycles),
        sync_stall_cycles_per_batch=safe_div(sync_stall_cycles, len(batches)),
        offchip_reduction_vs_no_sharing=1.0 - safe_div(
            sum(batch.memory_bytes for batch in batches),
            sum(batch.no_oats_memory_bytes for batch in batches),
        ),
        latency_ms_avg=mean(latencies),
        latency_ms_p50=percentile(latencies, 50),
        latency_ms_p95=percentile(latencies, 95),
        latency_ms_p99=percentile(latencies, 99),
        batching_span_p50=percentile(spans, 50),
        batching_span_p95=percentile(spans, 95),
        batching_span_p99=percentile(spans, 99),
        notes=(
            "Real TGL edge stream; memory reduction is vs no-sharing/no-OATS, "
            "separate from the RTGA comparison run. Sync stall is a cycle-model proxy."
        ),
    )


def empty_summary(
    dataset: str,
    model: str,
    coverage: str,
    events: int,
    vertices: int,
    batch_size: int,
    frequency_mhz: float,
) -> SummaryCounters:
    model_cfg = MODEL_PROFILES[model]
    return SummaryCounters(
        dataset=dataset,
        model=model,
        coverage=coverage,
        events=events,
        vertices=vertices,
        batches=0,
        batch_size=batch_size,
        endpoint=str(model_cfg["endpoint"]),
        fanout=int(model_cfg["fanout"]),
        depth=int(model_cfg["depth"]),
        tdp_entries=0,
        frequency_mhz=frequency_mhz,
        total_packets=0,
        memory_packets=0,
        hash_hits=0,
        packet_hit_rate=0.0,
        packet_reuse_rate=0.0,
        packet_reuse_factor=0.0,
        hash_collision_insert_rate=0.0,
        full_bucket_fallback_rate=0.0,
        collision_probe_per_insert=0.0,
        sync_stall_rate=0.0,
        sync_stall_cycles_per_batch=0.0,
        offchip_reduction_vs_no_sharing=0.0,
        latency_ms_avg=0.0,
        latency_ms_p50=0.0,
        latency_ms_p95=0.0,
        latency_ms_p99=0.0,
        batching_span_p50=0.0,
        batching_span_p95=0.0,
        batching_span_p99=0.0,
        notes="No batches profiled.",
    )


def aggregate_summaries(summaries: Sequence[SummaryCounters], by: str) -> list[SummaryCounters]:
    groups: dict[str, list[SummaryCounters]] = {}
    for item in summaries:
        key = getattr(item, by)
        groups.setdefault(key, []).append(item)

    aggregated: list[SummaryCounters] = []
    for key, items in groups.items():
        total_packets = sum(item.total_packets for item in items)
        memory_packets = sum(item.memory_packets for item in items)
        hash_hits = sum(item.hash_hits for item in items)
        insert_attempts = sum(item.memory_packets for item in items)
        colliding_inserts = sum(item.hash_collision_insert_rate * item.memory_packets for item in items)
        full_bucket_fallbacks = sum(item.full_bucket_fallback_rate * item.memory_packets for item in items)
        collision_probes = sum(item.collision_probe_per_insert * item.memory_packets for item in items)
        forward_cycles = sum(
            int(round(item.latency_ms_avg * item.frequency_mhz * 1000.0 * item.batches))
            for item in items
        )
        sync_stall_cycles = sum(item.sync_stall_cycles_per_batch * item.batches for item in items)
        label_dataset = key if by == "dataset" else "ALL"
        label_model = key if by == "model" else "ALL"
        aggregated.append(
            SummaryCounters(
                dataset=label_dataset,
                model=label_model,
                coverage="mixed",
                events=sum(item.events for item in items),
                vertices=sum(item.vertices for item in items),
                batches=sum(item.batches for item in items),
                batch_size=items[0].batch_size,
                endpoint="mixed",
                fanout=-1,
                depth=-1,
                tdp_entries=items[0].tdp_entries,
                frequency_mhz=items[0].frequency_mhz,
                total_packets=total_packets,
                memory_packets=memory_packets,
                hash_hits=hash_hits,
                packet_hit_rate=safe_div(hash_hits, total_packets),
                packet_reuse_rate=1.0 - safe_div(memory_packets, total_packets),
                packet_reuse_factor=safe_div(total_packets, memory_packets),
                hash_collision_insert_rate=safe_div(colliding_inserts, insert_attempts),
                full_bucket_fallback_rate=safe_div(full_bucket_fallbacks, insert_attempts),
                collision_probe_per_insert=safe_div(collision_probes, insert_attempts),
                sync_stall_rate=safe_div(sync_stall_cycles, forward_cycles),
                sync_stall_cycles_per_batch=safe_div(sync_stall_cycles, sum(item.batches for item in items)),
                offchip_reduction_vs_no_sharing=1.0 - safe_div(memory_packets, total_packets),
                latency_ms_avg=weighted_mean([item.latency_ms_avg for item in items], [item.batches for item in items]),
                latency_ms_p50=weighted_mean([item.latency_ms_p50 for item in items], [item.batches for item in items]),
                latency_ms_p95=weighted_mean([item.latency_ms_p95 for item in items], [item.batches for item in items]),
                latency_ms_p99=weighted_mean([item.latency_ms_p99 for item in items], [item.batches for item in items]),
                batching_span_p50=weighted_mean([item.batching_span_p50 for item in items], [item.batches for item in items]),
                batching_span_p95=weighted_mean([item.batching_span_p95 for item in items], [item.batches for item in items]),
                batching_span_p99=weighted_mean([item.batching_span_p99 for item in items], [item.batches for item in items]),
                notes="Weighted aggregate over profiled dataset/model rows.",
            )
        )
    return aggregated


def write_csv(path: Path, rows: Sequence[object], row_type: type) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(row_type.__dataclass_fields__.keys())  # type: ignore[attr-defined]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_markdown(path: Path, summaries: Sequence[SummaryCounters]) -> None:
    lines = [
        "# Q14 OATS Counter Profile",
        "",
        "This table is generated from real TGL edge streams with the current TempGNN dependency/PHLE cycle model.",
        "Model names are explicit dependency-scope profiles for the current HLS kernel, not trained checkpoints.",
        "Memory reduction is versus a no-sharing/no-OATS baseline and is reported as an internal OATS counter profile.",
        "",
        "| Dataset | Model | Coverage | Fanout | Depth | Batches | Packet hit | Packet reuse | Reuse factor | Collision inserts | Full-bucket fallback | Sync stall | Off-chip reduction | P50 ms | P95 ms | P99 ms |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summaries:
        lines.append(
            f"| {item.dataset} | {item.model} | {item.coverage} | "
            f"{item.fanout} | {item.depth} | {item.batches} | "
            f"{pct(item.packet_hit_rate)} | {pct(item.packet_reuse_rate)} | "
            f"{item.packet_reuse_factor:.3f}x | {pct(item.hash_collision_insert_rate)} | "
            f"{pct(item.full_bucket_fallback_rate)} | {pct(item.sync_stall_rate)} | "
            f"{pct(item.offchip_reduction_vs_no_sharing)} | "
            f"{item.latency_ms_p50:.4f} | {item.latency_ms_p95:.4f} | {item.latency_ms_p99:.4f} |"
        )
    lines.extend(
        [
            "",
            "Metric definitions:",
            "",
            "- Packet hit = PHLE lookup hits / total packet references.",
            "- Packet reuse = 1 - memory packet fetches / total packet references.",
            "- Collision inserts = inserts whose hash bucket already held a nonmatching entry.",
            "- Full-bucket fallback = nonmatching insert attempts into a full 4-way bucket, treated as non-shared.",
            "- Sync stall = critical-path wait cycles not covered by parallel packet fetch cycles, divided by modeled forward cycles.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = math.ceil((p / 100.0) * len(ordered))
    return ordered[max(0, min(len(ordered) - 1, rank - 1))]


def cycles_to_ms(cycles: int, frequency_mhz: float) -> float:
    return cycles / (frequency_mhz * 1000.0)


def ceil_div(value: int, divisor: int) -> int:
    return 0 if divisor == 0 else (value + divisor - 1) // divisor


def safe_div(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def weighted_mean(values: Sequence[float], weights: Sequence[int]) -> float:
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    return sum(value * weight for value, weight in zip(values, weights)) / total_weight


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


if __name__ == "__main__":
    main()
