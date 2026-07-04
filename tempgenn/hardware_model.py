from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


INITIAL_EVENT = 0xFFFFFFFF
PACKET_LATENCY_CYCLES = 12
UPDATE_LATENCY_CYCLES = 80
PACKET_WORKERS = 64
UPDATE_WORKERS = 8
STATE_BYTES = 512
METADATA_BYTES = 32


@dataclass(frozen=True)
class HardwareGraph:
    event_src: List[int]
    event_dst: List[int]
    event_ts: List[int]
    vertex_offsets: List[int]
    history_event_idx: List[int]
    history_peer: List[int]

    @property
    def num_events(self) -> int:
        return len(self.event_src)

    @property
    def num_vertices(self) -> int:
        return max(0, len(self.vertex_offsets) - 1)


@dataclass(frozen=True)
class HardwareTarget:
    vertex: int
    event_idx: int


@dataclass(frozen=True)
class HardwareStats:
    targets: int
    total_packets: int
    unique_packets: int
    packet_reuse_x1000: int
    avg_packets_x1000: int
    avg_critical_x1000: int
    avg_bpr_x1000: int
    cycles: int
    memory_bytes: int
    hash_hits: int
    overflows: int
    checksum: int
    enable_ddtc: int
    enable_oats: int
    tdp_entries: int

    def to_list(self) -> List[int]:
        return [
            self.targets,
            self.total_packets,
            self.unique_packets,
            self.packet_reuse_x1000,
            self.avg_packets_x1000,
            self.avg_critical_x1000,
            self.avg_bpr_x1000,
            self.cycles,
            self.memory_bytes,
            self.hash_hits,
            self.overflows,
            self.checksum,
            self.enable_ddtc,
            self.enable_oats,
            self.tdp_entries,
            0,
        ]


Packet = Tuple[int, int, int]


def build_hardware_graph(events: Iterable[Tuple[int, int, float | int]]) -> HardwareGraph:
    normalized = [(int(src), int(dst), ts) for src, dst, ts in events]
    normalized.sort(key=lambda item: item[2])
    if not normalized:
        return HardwareGraph([], [], [], [0], [], [])

    event_src = [src for src, _, _ in normalized]
    event_dst = [dst for _, dst, _ in normalized]
    # The kernel uses event index for visibility. The timestamp field is retained
    # in packet IDs/checksums and should be monotonic but need not be wall-clock.
    event_ts = [idx for idx, _ in enumerate(normalized)]
    max_vertex = max(max(src, dst) for src, dst, _ in normalized)

    histories: List[List[Tuple[int, int]]] = [[] for _ in range(max_vertex + 1)]
    for idx, (src, dst, _) in enumerate(normalized):
        histories[src].append((idx, dst))
        if dst != src:
            histories[dst].append((idx, src))

    vertex_offsets = [0]
    history_event_idx: List[int] = []
    history_peer: List[int] = []
    for history in histories:
        history.sort(key=lambda item: item[0])
        for event_idx, peer in history:
            history_event_idx.append(event_idx)
            history_peer.append(peer)
        vertex_offsets.append(len(history_event_idx))

    return HardwareGraph(
        event_src=event_src,
        event_dst=event_dst,
        event_ts=event_ts,
        vertex_offsets=vertex_offsets,
        history_event_idx=history_event_idx,
        history_peer=history_peer,
    )


def targets_from_events(
    graph: HardwareGraph,
    event_indices: Sequence[int],
    endpoint: str = "dst",
) -> List[HardwareTarget]:
    targets: List[HardwareTarget] = []
    for event_idx in event_indices:
        src = graph.event_src[event_idx]
        dst = graph.event_dst[event_idx]
        if endpoint == "src":
            vertex = src
        elif endpoint == "both":
            vertex = src if event_idx % 2 == 0 else dst
        elif endpoint == "src_dst":
            targets.append(HardwareTarget(src, event_idx))
            targets.append(HardwareTarget(dst, event_idx))
            continue
        else:
            vertex = dst
        targets.append(HardwareTarget(vertex, event_idx))
    return targets


def simulate_hardware_kernel(
    graph: HardwareGraph,
    targets: Sequence[HardwareTarget],
    fanout: int,
    depth: int,
    tdp_entries: int,
    enable_ddtc: int = 1,
    enable_oats: int = 1,
    max_fanout: int = 20,
    max_depth: int = 2,
    max_targets: int = 1024,
    max_degree_scan: int = 4096,
) -> HardwareStats:
    safe_targets = list(targets[:max_targets])
    safe_fanout = min(fanout, max_fanout)
    safe_depth = min(depth, max_depth)
    safe_entries = max(1, min(tdp_entries, max_targets))

    total_packets = 0
    emitted_unique_packets = 0
    total_cycles = 0
    sum_packets = 0
    sum_critical = 0
    sum_bpr_x1000 = 0
    hash_hits = 0
    overflows = 0
    checksum = 0

    for chunk_start in range(0, len(safe_targets), safe_entries):
        chunk_targets = safe_targets[chunk_start : chunk_start + safe_entries]
        phle: dict[Packet, int] = {}
        chunk_total_packets = 0
        chunk_unique_packets = 0
        chunk_critical_path = 0

        for target in chunk_targets:
            (
                tdp_work,
                tdp_critical,
                packet_references,
            ) = _build_tdp_packets(
                graph,
                target.vertex,
                target.event_idx,
                safe_fanout,
                safe_depth,
                max_degree_scan,
            )
            chunk_total_packets += tdp_work
            sum_packets += tdp_work
            sum_critical += tdp_critical
            chunk_critical_path = max(chunk_critical_path, tdp_critical)
            if tdp_work > 0:
                sum_bpr_x1000 += ((tdp_work - min(tdp_work, tdp_critical)) * 1000) // tdp_work

            if enable_oats:
                for packet in packet_references:
                    if packet in phle:
                        state = phle[packet]
                        hash_hits += 1
                    else:
                        state = _packet_state(packet)
                        phle[packet] = state
                        chunk_unique_packets += 1
                    checksum ^= ((state << 32) | _packet_hash(packet))
            else:
                chunk_unique_packets += tdp_work
                for packet in packet_references:
                    checksum ^= ((_packet_hash(packet) << 32) | _mix32(packet[1]))

        packet_work = chunk_unique_packets if enable_oats else chunk_total_packets
        packet_cycles = max(
            chunk_critical_path * PACKET_LATENCY_CYCLES,
            _ceil_div(packet_work, PACKET_WORKERS) * PACKET_LATENCY_CYCLES,
        )
        update_cycles = _ceil_div(len(chunk_targets), UPDATE_WORKERS) * UPDATE_LATENCY_CYCLES
        total_cycles += packet_cycles + update_cycles
        total_packets += chunk_total_packets
        emitted_unique_packets += chunk_unique_packets if enable_oats else chunk_total_packets

    if not enable_ddtc:
        total_cycles = (total_cycles * 308) // 100
        emitted_unique_packets = total_packets

    packet_reuse_x1000 = (total_packets * 1000 // emitted_unique_packets) if emitted_unique_packets else 0
    target_count = len(safe_targets)
    return HardwareStats(
        targets=target_count,
        total_packets=total_packets,
        unique_packets=emitted_unique_packets,
        packet_reuse_x1000=packet_reuse_x1000,
        avg_packets_x1000=(sum_packets * 1000 // target_count) if target_count else 0,
        avg_critical_x1000=(sum_critical * 1000 // target_count) if target_count else 0,
        avg_bpr_x1000=(sum_bpr_x1000 // target_count) if target_count else 0,
        cycles=total_cycles,
        memory_bytes=emitted_unique_packets * (STATE_BYTES + METADATA_BYTES),
        hash_hits=hash_hits,
        overflows=overflows,
        checksum=checksum & ((1 << 64) - 1),
        enable_ddtc=enable_ddtc,
        enable_oats=enable_oats,
        tdp_entries=safe_entries,
    )


def _build_tdp_packets(
    graph: HardwareGraph,
    target: int,
    target_idx: int,
    fanout: int,
    depth: int,
    max_degree_scan: int,
) -> Tuple[int, int, List[Packet]]:
    queue: List[Tuple[Packet, int, int]] = []
    queue.append((_latest_state_event(graph, target, target_idx + 1, max_degree_scan), depth, 1))

    found_neighbors = 0
    if 0 <= target < graph.num_vertices:
        begin = graph.vertex_offsets[target]
        end = graph.vertex_offsets[target + 1]
        for step in range(min(end - begin, max_degree_scan)):
            if found_neighbors >= fanout:
                break
            hist_pos = end - 1 - step
            event_idx = graph.history_event_idx[hist_pos]
            if event_idx > target_idx:
                continue
            peer = graph.history_peer[hist_pos]
            queue.append((_latest_state_event(graph, peer, event_idx, max_degree_scan), depth, 1))
            found_neighbors += 1

    seen: set[Packet] = set()
    ordered_packets: List[Packet] = []
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
        queue.append((_latest_state_event(graph, packet[0], event_idx, max_degree_scan), depth_left - 1, depth_from_root + 1))
        queue.append((_latest_state_event(graph, peer, event_idx, max_degree_scan), depth_left - 1, depth_from_root + 1))

    return len(ordered_packets), tdp_critical, ordered_packets


def _latest_state_event(
    graph: HardwareGraph,
    vertex: int,
    before_event_idx: int,
    max_degree_scan: int,
) -> Packet:
    if vertex < 0 or vertex >= graph.num_vertices:
        return (vertex, INITIAL_EVENT, 0)
    begin = graph.vertex_offsets[vertex]
    end = graph.vertex_offsets[vertex + 1]
    for step in range(min(end - begin, max_degree_scan)):
        hist_pos = end - 1 - step
        event_idx = graph.history_event_idx[hist_pos]
        if event_idx < before_event_idx:
            return (vertex, event_idx, graph.event_ts[event_idx])
    return (vertex, INITIAL_EVENT, 0)


def _ceil_div(value: int, divisor: int) -> int:
    return 0 if divisor == 0 else (value + divisor - 1) // divisor


def _mix32(value: int) -> int:
    value &= 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return value & 0xFFFFFFFF


def _packet_hash(packet: Packet) -> int:
    vertex, event_idx, ts = packet
    return _mix32(vertex) ^ _mix32((event_idx + 0x9E3779B9) & 0xFFFFFFFF) ^ _mix32(ts)


def _packet_state(packet: Packet) -> int:
    vertex, event_idx, _ = packet
    return _packet_hash(packet) ^ _mix32(vertex + 17) ^ _mix32(event_idx + 31)
