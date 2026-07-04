from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from math import ceil
from typing import Dict, Iterable, List, Sequence

from .graph import PacketKey, TargetQuery, TemporalGraph
from .tdp import TDP, TDPBuilder


@dataclass
class SimulationConfig:
    fanout: int = 20
    depth: int = 2
    tdp_entries: int = 16
    packet_workers: int = 64
    update_workers: int = 8
    packet_latency_cycles: int = 12
    update_latency_cycles: int = 80
    state_bytes: int = 512
    metadata_bytes: int = 32
    frequency_mhz: float = 225.0
    ddtc_scan_amplification: float = 3.08


@dataclass
class BatchMetrics:
    targets: int
    fanout: int
    depth: int
    tdp_entries: int
    total_tdp_packets: int
    unique_tdp_packets: int
    packet_reuse_factor: float
    avg_packets_per_target: float
    avg_critical_path: float
    avg_branch_parallelism_ratio: float
    top_hot_vertex_access_ratio: float
    cascade_proxy_cycles: int
    wo_ddtc_cycles: int
    wo_oats_cycles: int
    tempgenn_cycles: int
    cascade_proxy_latency_ms: float
    tempgenn_latency_ms: float
    speedup_vs_cascade_proxy: float
    speedup_vs_wo_ddtc: float
    speedup_vs_wo_oats: float
    cascade_proxy_memory_mb: float
    tempgenn_memory_mb: float
    memory_reduction_vs_cascade: float

    def as_dict(self) -> Dict[str, float | int]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True)


def simulate_batch(
    graph: TemporalGraph,
    targets: Sequence[TargetQuery],
    config: SimulationConfig,
) -> BatchMetrics:
    builder = TDPBuilder(graph, fanout=config.fanout, depth=config.depth)
    tdps = builder.build_many(list(targets))

    total_packets = sum(tdp.work for tdp in tdps)
    unique_packets = len(_unique_non_initial_packets(tdps))
    packet_reuse = _safe_div(total_packets, unique_packets)

    critical_paths = [tdp.critical_path_length for tdp in tdps]
    branch_ratios = [tdp.branch_parallelism_ratio for tdp in tdps]
    avg_critical = _safe_div(sum(critical_paths), len(critical_paths))
    avg_bpr = _safe_div(sum(branch_ratios), len(branch_ratios))

    cascade_cycles = (
        total_packets * config.packet_latency_cycles
        + len(tdps) * config.update_latency_cycles
    )
    wo_ddtc_cycles = int(ceil(cascade_cycles * config.ddtc_scan_amplification))
    wo_oats_cycles = _estimate_chunked_cycles(tdps, config, overlap_aware=False)
    tempgenn_cycles = _estimate_chunked_cycles(tdps, config, overlap_aware=True)

    cascade_bytes = total_packets * (config.state_bytes + config.metadata_bytes)
    tempgenn_bytes = unique_packets * (config.state_bytes + config.metadata_bytes)

    return BatchMetrics(
        targets=len(targets),
        fanout=config.fanout,
        depth=config.depth,
        tdp_entries=config.tdp_entries,
        total_tdp_packets=total_packets,
        unique_tdp_packets=unique_packets,
        packet_reuse_factor=packet_reuse,
        avg_packets_per_target=_safe_div(total_packets, len(tdps)),
        avg_critical_path=avg_critical,
        avg_branch_parallelism_ratio=avg_bpr,
        top_hot_vertex_access_ratio=_top_hot_vertex_ratio(tdps, fraction=0.005),
        cascade_proxy_cycles=cascade_cycles,
        wo_ddtc_cycles=wo_ddtc_cycles,
        wo_oats_cycles=wo_oats_cycles,
        tempgenn_cycles=tempgenn_cycles,
        cascade_proxy_latency_ms=_cycles_to_ms(cascade_cycles, config.frequency_mhz),
        tempgenn_latency_ms=_cycles_to_ms(tempgenn_cycles, config.frequency_mhz),
        speedup_vs_cascade_proxy=_safe_div(cascade_cycles, tempgenn_cycles),
        speedup_vs_wo_ddtc=_safe_div(wo_ddtc_cycles, tempgenn_cycles),
        speedup_vs_wo_oats=_safe_div(wo_oats_cycles, tempgenn_cycles),
        cascade_proxy_memory_mb=cascade_bytes / (1024 * 1024),
        tempgenn_memory_mb=tempgenn_bytes / (1024 * 1024),
        memory_reduction_vs_cascade=1.0 - _safe_div(tempgenn_bytes, cascade_bytes),
    )


def _estimate_chunked_cycles(
    tdps: Sequence[TDP],
    config: SimulationConfig,
    overlap_aware: bool,
) -> int:
    total_cycles = 0
    for chunk in _chunks(tdps, max(1, config.tdp_entries)):
        chunk_critical = max((tdp.critical_path_length for tdp in chunk), default=0)
        if overlap_aware:
            packet_work = len(_unique_non_initial_packets(chunk))
        else:
            packet_work = sum(tdp.work for tdp in chunk)

        packet_cycles = max(
            chunk_critical * config.packet_latency_cycles,
            ceil(packet_work / max(1, config.packet_workers)) * config.packet_latency_cycles,
        )
        update_cycles = ceil(len(chunk) / max(1, config.update_workers)) * config.update_latency_cycles
        total_cycles += packet_cycles + update_cycles
    return max(1, total_cycles)


def _unique_non_initial_packets(tdps: Iterable[TDP]) -> set[PacketKey]:
    packets: set[PacketKey] = set()
    for tdp in tdps:
        packets.update(tdp.non_initial_packets())
    return packets


def _top_hot_vertex_ratio(tdps: Sequence[TDP], fraction: float) -> float:
    counts: Dict[int, int] = {}
    total = 0
    for tdp in tdps:
        for packet in tdp.non_initial_packets():
            counts[packet.vertex] = counts.get(packet.vertex, 0) + 1
            total += 1
    if total == 0 or not counts:
        return 0.0
    hot_count = max(1, int(len(counts) * fraction))
    hot_accesses = sum(sorted(counts.values(), reverse=True)[:hot_count])
    return hot_accesses / total


def _cycles_to_ms(cycles: int, frequency_mhz: float) -> float:
    return cycles / (frequency_mhz * 1000.0)


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _chunks(items: Sequence[TDP], size: int) -> Iterable[Sequence[TDP]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
