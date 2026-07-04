from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Iterable, List

from tempgenn.data import load_temporal_csv
from tempgenn.hardware_model import (
    HardwareTarget,
    build_hardware_graph,
    simulate_hardware_kernel,
    targets_from_events,
)
from tempgenn.synthetic import generate_synthetic_graph

FWD_DIM = 8
FWD_SCALE = 1024
FWD_MAX_DEPTH = 8
MAX_FANOUT = 20
MAX_TARGETS = 1024
MAX_QUEUE = 4096
MAX_LOCAL_PACKETS = 4096
HASH_BUCKETS = 2048
HASH_WAYS = 4
HASH_SIZE = HASH_BUCKETS * HASH_WAYS
MAX_DEGREE_SCAN = 4096
PACKET_LATENCY_CYCLES = 12
UPDATE_LATENCY_CYCLES = 80
PACKET_WORKERS = 64
UPDATE_WORKERS = 8
METADATA_BYTES = 32
INITIAL_EVENT = 0xFFFFFFFF
MASK64 = (1 << 64) - 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Export TempGNN HLS/XRT fixture arrays.")
    parser.add_argument("--data", type=Path, help="CSV edge stream. If omitted, synthetic data is used.")
    parser.add_argument("--src-column")
    parser.add_argument("--dst-column")
    parser.add_argument("--time-column")
    parser.add_argument("--vertices", type=int, default=512)
    parser.add_argument("--events", type=int, default=8192)
    parser.add_argument("--target-events", type=int, default=1024)
    parser.add_argument("--endpoint", choices=["src", "dst", "both", "src_dst"], default="dst")
    parser.add_argument("--fanout", type=int, default=20)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--tdp-entries", type=int, default=16)
    parser.add_argument("--out", type=Path, default=Path("results/hardware_fixture"))
    args = parser.parse_args()

    if args.data:
        loaded_graph = load_temporal_csv(
            args.data,
            src_column=args.src_column,
            dst_column=args.dst_column,
            time_column=args.time_column,
            limit=args.events,
        )
        events = [(event.src, event.dst, event.ts) for event in loaded_graph.events]
    else:
        generated_graph = generate_synthetic_graph(
            vertices=args.vertices,
            edges=args.events,
            seed=7,
        )
        events = [(event.src, event.dst, event.ts) for event in generated_graph.events]

    graph = build_hardware_graph(events)
    event_indices = list(range(max(0, graph.num_events - args.target_events), graph.num_events))
    targets: List[HardwareTarget] = targets_from_events(graph, event_indices, endpoint=args.endpoint)

    args.out.mkdir(parents=True, exist_ok=True)
    _write_u32(args.out / "event_src.bin", graph.event_src)
    _write_u32(args.out / "event_dst.bin", graph.event_dst)
    _write_u32(args.out / "event_ts.bin", graph.event_ts)
    _write_u32(args.out / "vertex_offsets.bin", graph.vertex_offsets)
    _write_u32(args.out / "history_event_idx.bin", graph.history_event_idx)
    _write_u32(args.out / "history_peer.bin", graph.history_peer)
    _write_u32(args.out / "target_vertex.bin", [target.vertex for target in targets])
    _write_u32(args.out / "target_event_idx.bin", [target.event_idx for target in targets])

    initial_memory, event_features, weight_self, weight_peer, weight_event, bias = _make_forward_inputs(
        graph.num_vertices,
        graph.num_events,
    )
    _write_i16(args.out / "initial_memory.bin", initial_memory)
    _write_i16(args.out / "event_features.bin", event_features)
    _write_i16(args.out / "weight_self.bin", weight_self)
    _write_i16(args.out / "weight_peer.bin", weight_peer)
    _write_i16(args.out / "weight_event.bin", weight_event)
    _write_i16(args.out / "bias.bin", bias)

    forward_stats, forward_embeddings = _simulate_forward_kernel(
        graph,
        targets,
        fanout=args.fanout,
        depth=args.depth,
        tdp_entries=args.tdp_entries,
        enable_ddtc=1,
        enable_oats=1,
        initial_memory=initial_memory,
        event_features=event_features,
        weight_self=weight_self,
        weight_peer=weight_peer,
        weight_event=weight_event,
        bias=bias,
    )
    _write_u64(args.out / "expected_stats.bin", forward_stats)
    _write_i16(args.out / "expected_embedding.bin", forward_embeddings)

    tempgnn_stats = simulate_hardware_kernel(
        graph,
        targets,
        fanout=args.fanout,
        depth=args.depth,
        tdp_entries=args.tdp_entries,
        enable_ddtc=1,
        enable_oats=1,
    )
    wo_oats_stats = simulate_hardware_kernel(
        graph,
        targets,
        fanout=args.fanout,
        depth=args.depth,
        tdp_entries=args.tdp_entries,
        enable_ddtc=1,
        enable_oats=0,
    )
    wo_ddtc_stats = simulate_hardware_kernel(
        graph,
        targets,
        fanout=args.fanout,
        depth=args.depth,
        tdp_entries=args.tdp_entries,
        enable_ddtc=0,
        enable_oats=1,
    )

    metadata = {
        "num_events": graph.num_events,
        "num_vertices": graph.num_vertices,
        "num_targets": len(targets),
        "fanout": args.fanout,
        "depth": args.depth,
        "tdp_entries": args.tdp_entries,
        "endpoint": args.endpoint,
        "stats": {
            "tempgenn": tempgnn_stats.to_list(),
            "wo_oats": wo_oats_stats.to_list(),
            "wo_ddtc": wo_ddtc_stats.to_list(),
        },
        "forward": {
            "dim": FWD_DIM,
            "stats": forward_stats,
            "embedding_words": len(forward_embeddings),
            "embedding0": forward_embeddings[:FWD_DIM],
        },
        "stat_indices": [
            "targets",
            "total_packets",
            "unique_packets",
            "packet_reuse_x1000",
            "avg_packets_x1000",
            "avg_critical_x1000",
            "avg_bpr_x1000",
            "cycles",
            "memory_bytes",
            "hash_hits",
            "overflows",
            "checksum",
            "enable_ddtc",
            "enable_oats",
            "tdp_entries",
            "reserved",
        ],
    }
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


def _write_u32(path: Path, values: Iterable[int]) -> None:
    vals = list(values)
    with path.open("wb") as handle:
        handle.write(struct.pack(f"<{len(vals)}I", *vals))


def _write_i16(path: Path, values: Iterable[int]) -> None:
    vals = list(values)
    with path.open("wb") as handle:
        handle.write(struct.pack(f"<{len(vals)}h", *vals))


def _write_u64(path: Path, values: Iterable[int]) -> None:
    vals = [value & MASK64 for value in values]
    with path.open("wb") as handle:
        handle.write(struct.pack(f"<{len(vals)}Q", *vals))


def _make_forward_inputs(num_vertices: int, num_events: int) -> tuple[List[int], List[int], List[int], List[int], List[int], List[int]]:
    initial_memory = [0] * (num_vertices * FWD_DIM)
    event_features = [0] * (num_events * FWD_DIM)
    for vertex in range(num_vertices):
        for dim in range(FWD_DIM):
            initial_memory[vertex * FWD_DIM + dim] = ((vertex + 3) * (dim + 5) * 17) % 257 - 128
    for event_idx in range(num_events):
        for dim in range(FWD_DIM):
            event_features[event_idx * FWD_DIM + dim] = ((event_idx + 1) * (dim + 7) * 23) % 1024 - 512

    weight_self = [640] * FWD_DIM
    weight_peer = [320] * FWD_DIM
    weight_event = [96 + dim * 8 for dim in range(FWD_DIM)]
    bias = [dim * 3 - 9 for dim in range(FWD_DIM)]
    return initial_memory, event_features, weight_self, weight_peer, weight_event, bias


def _simulate_forward_kernel(
    graph,
    targets: List[HardwareTarget],
    fanout: int,
    depth: int,
    tdp_entries: int,
    enable_ddtc: int,
    enable_oats: int,
    initial_memory: List[int],
    event_features: List[int],
    weight_self: List[int],
    weight_peer: List[int],
    weight_event: List[int],
    bias: List[int],
) -> tuple[List[int], List[int]]:
    safe_targets = targets[:MAX_TARGETS]
    safe_events = min(graph.num_events, 8192)
    safe_vertices = min(graph.num_vertices, 16384)
    safe_entries = max(1, min(tdp_entries, MAX_TARGETS))

    total_packets = 0
    emitted_unique_packets = 0
    total_cycles = 0
    sum_packets = 0
    sum_critical = 0
    sum_bpr_x1000 = 0
    hash_hits = 0
    overflow_count = 0
    checksum = 0
    embedding_out = [0] * (len(safe_targets) * FWD_DIM)

    for chunk_start in range(MAX_TARGETS):
        if chunk_start >= len(safe_targets):
            break
        if (chunk_start % safe_entries) != 0:
            continue

        phle_key: List[tuple[int, int, int] | None] = [None] * HASH_SIZE
        phle_state: List[List[int] | None] = [None] * HASH_SIZE
        chunk_end = min(chunk_start + safe_entries, len(safe_targets))
        chunk_targets = chunk_end - chunk_start
        chunk_total_packets = 0
        chunk_unique_packets = 0
        chunk_critical_path = 0

        for offset in range(chunk_targets):
            target_pos = chunk_start + offset
            target = safe_targets[target_pos]
            if target.event_idx >= safe_events:
                overflow_count += 1
                target_embedding = _load_initial_state(initial_memory, safe_vertices, target.vertex)
            else:
                result = _process_forward_target(
                    graph,
                    safe_events,
                    safe_vertices,
                    target.vertex,
                    target.event_idx,
                    fanout,
                    depth,
                    enable_oats,
                    initial_memory,
                    event_features,
                    weight_self,
                    weight_peer,
                    weight_event,
                    bias,
                    phle_key,
                    phle_state,
                )
                target_embedding = result["embedding"]
                chunk_total_packets += result["chunk_total_packets"]
                chunk_unique_packets += result["chunk_unique_packets"]
                chunk_critical_path = max(chunk_critical_path, result["chunk_critical_path"])
                sum_packets += result["sum_packets"]
                sum_critical += result["sum_critical"]
                sum_bpr_x1000 += result["sum_bpr_x1000"]
                hash_hits += result["hash_hits"]
                overflow_count += result["overflow_count"]
                checksum ^= result["checksum"]
                checksum &= MASK64

            for dim, value in enumerate(target_embedding):
                embedding_out[target_pos * FWD_DIM + dim] = value
                checksum ^= (_u16(value) << ((dim & 3) * 16))
                checksum &= MASK64

        packet_work = chunk_unique_packets if enable_oats else chunk_total_packets
        packet_cycles_parallel = _ceil_div(packet_work, PACKET_WORKERS) * PACKET_LATENCY_CYCLES
        packet_cycles_critical = chunk_critical_path * PACKET_LATENCY_CYCLES
        packet_cycles = max(packet_cycles_parallel, packet_cycles_critical)
        forward_cycles = _ceil_div(packet_work, UPDATE_WORKERS) * UPDATE_LATENCY_CYCLES
        total_cycles += packet_cycles + forward_cycles
        total_packets += chunk_total_packets
        emitted_unique_packets += chunk_unique_packets if enable_oats else chunk_total_packets

    if enable_ddtc == 0:
        total_cycles = (total_cycles * 308) // 100
        emitted_unique_packets = total_packets

    target_count = len(safe_targets)
    packet_reuse_x1000 = (total_packets * 1000 // emitted_unique_packets) if emitted_unique_packets else 0
    stats = [
        target_count,
        total_packets,
        emitted_unique_packets,
        packet_reuse_x1000,
        (sum_packets * 1000 // target_count) if target_count else 0,
        (sum_critical * 1000 // target_count) if target_count else 0,
        (sum_bpr_x1000 // target_count) if target_count else 0,
        total_cycles,
        emitted_unique_packets * (FWD_DIM * 2 + METADATA_BYTES),
        hash_hits,
        overflow_count,
        checksum & MASK64,
        enable_ddtc,
        enable_oats,
        safe_entries,
        0,
    ]
    return stats, embedding_out


def _process_forward_target(
    graph,
    safe_events: int,
    safe_vertices: int,
    target: int,
    target_idx: int,
    fanout: int,
    depth: int,
    enable_oats: int,
    initial_memory: List[int],
    event_features: List[int],
    weight_self: List[int],
    weight_peer: List[int],
    weight_event: List[int],
    bias: List[int],
    phle_key: List[tuple[int, int, int] | None],
    phle_state: List[List[int] | None],
):
    safe_depth = min(depth, FWD_MAX_DEPTH)
    safe_fanout = min(fanout, MAX_FANOUT)
    queue: List[tuple[tuple[int, int, int], int, int]] = []
    local_packets: List[tuple[int, int, int]] = []
    local_valid: List[bool] = []
    local_states: List[List[int]] = []

    overflow_count = 0
    chunk_total_packets = 0
    chunk_unique_packets = 0
    chunk_critical_path = 0
    sum_packets = 0
    sum_critical = 0
    sum_bpr_x1000 = 0
    hash_hits = 0
    checksum = 0

    def enqueue(packet: tuple[int, int, int], depth_left: int, depth_from_root: int) -> None:
        nonlocal overflow_count
        if len(queue) >= MAX_QUEUE:
            overflow_count += 1
            return
        queue.append((packet, depth_left, depth_from_root))

    self_root = _latest_state_event(graph, safe_vertices, safe_events, target, target_idx + 1)
    enqueue(self_root, safe_depth, 1)

    found_neighbors = 0
    if 0 <= target < safe_vertices:
        begin = graph.vertex_offsets[target]
        end = graph.vertex_offsets[target + 1]
        for step in range(min(end - begin, MAX_DEGREE_SCAN)):
            if found_neighbors >= safe_fanout:
                break
            hist_pos = end - 1 - step
            event_idx = graph.history_event_idx[hist_pos]
            if event_idx > target_idx or event_idx >= safe_events:
                continue
            peer = graph.history_peer[hist_pos]
            peer_root = _latest_state_event(graph, safe_vertices, safe_events, peer, event_idx)
            enqueue(peer_root, safe_depth, 1)
            found_neighbors += 1

    head = 0
    while head < len(queue) and head < MAX_QUEUE:
        packet, depth_left, depth_from_root = queue[head]
        head += 1
        if packet[1] == INITIAL_EVENT:
            continue
        if _find_local_packet(local_packets, packet) is not None:
            continue
        if len(local_packets) >= MAX_LOCAL_PACKETS:
            overflow_count += 1
            continue

        local_packets.append(packet)
        local_valid.append(False)
        local_states.append([0] * FWD_DIM)
        chunk_total_packets += 1
        chunk_critical_path = max(chunk_critical_path, depth_from_root)

        if depth_left == 0 or packet[1] >= safe_events:
            continue

        src = graph.event_src[packet[1]]
        dst = graph.event_dst[packet[1]]
        peer = dst if src == packet[0] else src
        self_dep = _latest_state_event(graph, safe_vertices, safe_events, packet[0], packet[1])
        peer_dep = _latest_state_event(graph, safe_vertices, safe_events, peer, packet[1])
        enqueue(self_dep, depth_left - 1, depth_from_root + 1)
        enqueue(peer_dep, depth_left - 1, depth_from_root + 1)

    for _ in range(MAX_LOCAL_PACKETS):
        if all(local_valid):
            break
        packet_idx = None
        best_event = INITIAL_EVENT
        for scan, packet in enumerate(local_packets):
            if not local_valid[scan] and packet[1] <= best_event:
                packet_idx = scan
                best_event = packet[1]
        if packet_idx is None:
            break

        packet = local_packets[packet_idx]
        reused, out_state, hit_checksum = _phle_lookup(phle_key, phle_state, packet) if enable_oats else (False, [], 0)
        if reused:
            hash_hits += 1
            checksum ^= hit_checksum
            checksum &= MASK64
        else:
            src = graph.event_src[packet[1]]
            dst = graph.event_dst[packet[1]]
            peer = dst if src == packet[0] else src
            self_dep = _latest_state_event(graph, safe_vertices, safe_events, packet[0], packet[1])
            peer_dep = _latest_state_event(graph, safe_vertices, safe_events, peer, packet[1])
            self_state = _dependency_state(initial_memory, safe_vertices, local_packets, local_valid, local_states, self_dep)
            peer_state = _dependency_state(initial_memory, safe_vertices, local_packets, local_valid, local_states, peer_dep)
            out_state = _update_state(graph, event_features, weight_self, weight_peer, weight_event, bias, self_state, peer_state, packet)
            chunk_unique_packets += 1
            if enable_oats:
                inserted, insert_checksum = _phle_insert(phle_key, phle_state, packet, out_state)
                if not inserted:
                    overflow_count += 1
                else:
                    checksum ^= insert_checksum
                    checksum &= MASK64
            else:
                local = _packet_hash(packet)
                for dim, value in enumerate(out_state):
                    local ^= (_u16(value) << ((dim & 3) * 16))
                checksum ^= local & MASK64
                checksum &= MASK64

        local_states[packet_idx] = out_state
        local_valid[packet_idx] = True

    root_idx = _find_local_packet(local_packets, self_root)
    if self_root[1] != INITIAL_EVENT and root_idx is not None and local_valid[root_idx]:
        embedding = list(local_states[root_idx])
    else:
        embedding = _load_initial_state(initial_memory, safe_vertices, target)

    sum_packets += len(local_packets)
    sum_critical += chunk_critical_path
    if local_packets:
        useful_parallel = max(0, len(local_packets) - chunk_critical_path)
        sum_bpr_x1000 += useful_parallel * 1000 // len(local_packets)

    return {
        "embedding": embedding,
        "chunk_total_packets": chunk_total_packets,
        "chunk_unique_packets": chunk_unique_packets,
        "chunk_critical_path": chunk_critical_path,
        "sum_packets": sum_packets,
        "sum_critical": sum_critical,
        "sum_bpr_x1000": sum_bpr_x1000,
        "hash_hits": hash_hits,
        "overflow_count": overflow_count,
        "checksum": checksum & MASK64,
    }


def _latest_state_event(graph, safe_vertices: int, safe_events: int, vertex: int, before_event_idx: int) -> tuple[int, int, int]:
    if vertex >= safe_vertices or vertex < 0:
        return (vertex, INITIAL_EVENT, 0)
    begin = graph.vertex_offsets[vertex]
    end = graph.vertex_offsets[vertex + 1]
    for step in range(min(end - begin, MAX_DEGREE_SCAN)):
        hist_pos = end - 1 - step
        event_idx = graph.history_event_idx[hist_pos]
        if event_idx < before_event_idx and event_idx < safe_events:
            return (vertex, event_idx, graph.event_ts[event_idx])
    return (vertex, INITIAL_EVENT, 0)


def _find_local_packet(packets: List[tuple[int, int, int]], packet: tuple[int, int, int]) -> int | None:
    for idx, existing in enumerate(packets):
        if existing[0] == packet[0] and existing[1] == packet[1]:
            return idx
    return None


def _dependency_state(
    initial_memory: List[int],
    safe_vertices: int,
    packets: List[tuple[int, int, int]],
    valid: List[bool],
    states: List[List[int]],
    dependency: tuple[int, int, int],
) -> List[int]:
    if dependency[1] == INITIAL_EVENT:
        return _load_initial_state(initial_memory, safe_vertices, dependency[0])
    dep_idx = _find_local_packet(packets, dependency)
    if dep_idx is not None and valid[dep_idx]:
        return list(states[dep_idx])
    return _load_initial_state(initial_memory, safe_vertices, dependency[0])


def _load_initial_state(initial_memory: List[int], safe_vertices: int, vertex: int) -> List[int]:
    if 0 <= vertex < safe_vertices:
        base = vertex * FWD_DIM
        return list(initial_memory[base : base + FWD_DIM])
    return [0] * FWD_DIM


def _update_state(
    graph,
    event_features: List[int],
    weight_self: List[int],
    weight_peer: List[int],
    weight_event: List[int],
    bias: List[int],
    self_state: List[int],
    peer_state: List[int],
    packet: tuple[int, int, int],
) -> List[int]:
    event_idx = packet[1]
    dst_side = packet[0] == graph.event_dst[event_idx]
    out: List[int] = []
    for dim in range(FWD_DIM):
        feature = event_features[event_idx * FWD_DIM + dim]
        if dst_side:
            feature = -feature
        acc = bias[dim]
        acc += _trunc_div(self_state[dim] * weight_self[dim], FWD_SCALE)
        acc += _trunc_div(peer_state[dim] * weight_peer[dim], FWD_SCALE)
        acc += _trunc_div(feature * weight_event[dim], FWD_SCALE)
        out.append(_hard_tanh_q10(acc))
    return out


def _phle_lookup(
    phle_key: List[tuple[int, int, int] | None],
    phle_state: List[List[int] | None],
    packet: tuple[int, int, int],
) -> tuple[bool, List[int], int]:
    bucket = _packet_hash(packet) % HASH_BUCKETS
    for way in range(HASH_WAYS):
        idx = bucket * HASH_WAYS + way
        key = phle_key[idx]
        if key is not None and key[0] == packet[0] and key[1] == packet[1]:
            state = list(phle_state[idx] or [0] * FWD_DIM)
            local = _packet_hash(packet)
            for dim, value in enumerate(state):
                local ^= _u16(value) << ((dim & 3) * 16)
            return True, state, local & MASK64
    return False, [], 0


def _phle_insert(
    phle_key: List[tuple[int, int, int] | None],
    phle_state: List[List[int] | None],
    packet: tuple[int, int, int],
    state: List[int],
) -> tuple[bool, int]:
    bucket = _packet_hash(packet) % HASH_BUCKETS
    empty_index = None
    for way in range(HASH_WAYS):
        idx = bucket * HASH_WAYS + way
        key = phle_key[idx]
        if key is not None:
            if key[0] == packet[0] and key[1] == packet[1]:
                return True, 0
        elif empty_index is None:
            empty_index = idx
    if empty_index is None:
        return False, 0

    phle_key[empty_index] = packet
    phle_state[empty_index] = list(state)
    local = _packet_hash(packet)
    for dim, value in enumerate(state):
        local ^= _u16(value) << ((dim & 3) * 16)
    return True, local & MASK64


def _ceil_div(value: int, divisor: int) -> int:
    return 0 if divisor == 0 else (value + divisor - 1) // divisor


def _trunc_div(value: int, divisor: int) -> int:
    if divisor == 0:
        return 0
    sign = -1 if (value < 0) ^ (divisor < 0) else 1
    return sign * (abs(value) // abs(divisor))


def _hard_tanh_q10(value: int) -> int:
    if value > FWD_SCALE:
        return FWD_SCALE
    if value < -FWD_SCALE:
        return -FWD_SCALE
    return max(-32768, min(32767, value))


def _u16(value: int) -> int:
    return value & 0xFFFF


def _mix32(value: int) -> int:
    value &= 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return value & 0xFFFFFFFF


def _packet_hash(packet: tuple[int, int, int]) -> int:
    vertex, event_idx, ts = packet
    return _mix32(vertex) ^ _mix32((event_idx + 0x9E3779B9) & 0xFFFFFFFF) ^ _mix32(ts)


if __name__ == "__main__":
    main()
