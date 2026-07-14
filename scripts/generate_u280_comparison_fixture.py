#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import sys
from array import array
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.export_hardware_fixture import _simulate_forward_kernel
from tempgenn.hardware_model import HardwareGraph, HardwareTarget


DIM = 8
MAX_EVENTS = 8192
DATASET_SEEDS = {"WK": 101, "MC": 211, "RT": 307, "LM": 401, "WT": 503, "GT": 601}
SYNTHETIC_SHAPES = {
    "WK": (2048, 256),
    "MC": (2560, 320),
    "RT": (3072, 384),
    "LM": (3584, 448),
    "WT": (4096, 512),
    "GT": (4608, 576),
}
MODELS = {
    "JODIE": {"id": 0, "fanout": 0, "depth": 1, "seed": 17},
    "TGN": {"id": 1, "fanout": 20, "depth": 2, "seed": 29},
    "TGAT": {"id": 2, "fanout": 20, "depth": 2, "seed": 43},
    "APAN": {"id": 3, "fanout": 10, "depth": 1, "seed": 59},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a bounded forward-path fixture from a real sample or explicit synthetic input."
    )
    parser.add_argument("--dataset", required=True, choices=DATASET_SEEDS)
    parser.add_argument("--model", required=True, choices=MODELS)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--input", type=Path, help="Normalized real sample with src,dst,time columns")
    parser.add_argument(
        "--synthetic", action="store_true", help="Use only for C-sim/development smoke tests"
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 1 <= args.batch_size <= 1024:
        raise SystemExit("batch size must be in 1..1024")
    if (args.input is None) == (not args.synthetic):
        raise SystemExit("select exactly one input mode: --input REAL_EDGES.csv or --synthetic")

    input_kind = "synthetic_smoke" if args.synthetic else "real_dataset_prefix"
    input_sha256 = "generated"
    source_metadata: dict[str, object] = {}
    if args.synthetic:
        event_src, event_dst, event_ts = synthetic_events(args.dataset)
        timestamp_mapping: dict[str, object] = {
            "method": "synthetic_event_index",
            "source_time_units_per_tick": 1.0,
            "origin": 0.0,
        }
    else:
        assert args.input is not None
        if not args.input.is_file():
            raise SystemExit(f"missing real dataset sample: {args.input}")
        event_src, event_dst, event_ts, timestamp_mapping = load_real_events(args.input)
        input_sha256 = sha256_file(args.input)
        source_metadata_path = args.input.with_name("metadata.json")
        if source_metadata_path.is_file():
            source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
            if source_metadata.get("input_kind") != input_kind:
                raise SystemExit(f"invalid real-sample metadata: {source_metadata_path}")
            if source_metadata.get("sample_sha256") != input_sha256:
                raise SystemExit(f"real-sample hash mismatch: {args.input}")

    num_events = len(event_src)
    if num_events < args.batch_size:
        raise SystemExit(f"input has {num_events} events, fewer than batch size {args.batch_size}")
    if num_events > MAX_EVENTS:
        event_src = event_src[:MAX_EVENTS]
        event_dst = event_dst[:MAX_EVENTS]
        event_ts = event_ts[:MAX_EVENTS]
        num_events = MAX_EVENTS
    num_vertices = max(max(event_src), max(event_dst)) + 1

    metadata_path = args.output / "metadata.json"
    if metadata_path.is_file() and not args.force:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("schema_version") == 4
            and metadata.get("dataset") == args.dataset
            and metadata.get("model") == args.model
            and metadata.get("batch_size") == args.batch_size
            and metadata.get("input_kind") == input_kind
            and metadata.get("input_sha256") == input_sha256
        ):
            print(args.output.resolve())
            return

    model = MODELS[args.model]
    seed = DATASET_SEEDS[args.dataset] * 1009 + int(model["seed"])
    rng = random.Random(seed)
    histories: list[list[tuple[int, int]]] = [[] for _ in range(num_vertices)]
    for event_idx, (src, dst) in enumerate(zip(event_src, event_dst)):
        histories[src].append((event_idx, dst))
        histories[dst].append((event_idx, src))

    vertex_offsets = [0]
    history_event_idx: list[int] = []
    history_peer: list[int] = []
    for history in histories:
        for event_idx, peer in history:
            history_event_idx.append(event_idx)
            history_peer.append(peer)
        vertex_offsets.append(len(history_event_idx))

    first_target_event = num_events - args.batch_size
    target_event_idx = list(range(first_target_event, num_events))
    target_vertex = [event_dst[event_idx] for event_idx in target_event_idx]
    initial_memory = [rng.randint(-256, 256) for _ in range(num_vertices * DIM)]
    event_features = [rng.randint(-192, 192) for _ in range(num_events * DIM)]

    model_id = int(model["id"])
    weight_self = [704 + model_id * 23 + dim * 5 for dim in range(DIM)]
    weight_peer = [448 + model_id * 31 + dim * 7 for dim in range(DIM)]
    weight_event = [320 + model_id * 19 + dim * 11 for dim in range(DIM)]
    bias = [((dim * 13 + model_id * 17) % 65) - 32 for dim in range(DIM)]

    args.output.mkdir(parents=True, exist_ok=True)
    files = {
        "event_src.bin": write_array(args.output / "event_src.bin", "I", event_src),
        "event_dst.bin": write_array(args.output / "event_dst.bin", "I", event_dst),
        "event_ts.bin": write_array(args.output / "event_ts.bin", "I", event_ts),
        "vertex_offsets.bin": write_array(args.output / "vertex_offsets.bin", "I", vertex_offsets),
        "history_event_idx.bin": write_array(
            args.output / "history_event_idx.bin", "I", history_event_idx
        ),
        "history_peer.bin": write_array(args.output / "history_peer.bin", "I", history_peer),
        "target_vertex.bin": write_array(args.output / "target_vertex.bin", "I", target_vertex),
        "target_event_idx.bin": write_array(
            args.output / "target_event_idx.bin", "I", target_event_idx
        ),
        "initial_memory.bin": write_array(args.output / "initial_memory.bin", "h", initial_memory),
        "event_features.bin": write_array(
            args.output / "event_features.bin", "h", event_features
        ),
        "weight_self.bin": write_array(args.output / "weight_self.bin", "h", weight_self),
        "weight_peer.bin": write_array(args.output / "weight_peer.bin", "h", weight_peer),
        "weight_event.bin": write_array(args.output / "weight_event.bin", "h", weight_event),
        "bias.bin": write_array(args.output / "bias.bin", "h", bias),
    }
    graph = HardwareGraph(
        event_src=event_src,
        event_dst=event_dst,
        event_ts=event_ts,
        vertex_offsets=vertex_offsets,
        history_event_idx=history_event_idx,
        history_peer=history_peer,
    )
    targets = [
        HardwareTarget(vertex=vertex, event_idx=event_idx)
        for vertex, event_idx in zip(target_vertex, target_event_idx)
    ]
    tempgnn_stats, tempgnn_embedding = _simulate_forward_kernel(
        graph,
        targets,
        fanout=int(model["fanout"]),
        depth=int(model["depth"]),
        tdp_entries=16,
        enable_ddtc=1,
        enable_oats=1,
        initial_memory=initial_memory,
        event_features=event_features,
        weight_self=weight_self,
        weight_peer=weight_peer,
        weight_event=weight_event,
        bias=bias,
    )
    files["expected_tempgnn_forward_kernel_embedding.bin"] = write_array(
        args.output / "expected_tempgnn_forward_kernel_embedding.bin",
        "h",
        tempgnn_embedding,
    )
    files["expected_tempgnn_forward_kernel_stats.bin"] = write_array(
        args.output / "expected_tempgnn_forward_kernel_stats.bin",
        "Q",
        tempgnn_stats,
    )
    metadata = {
        "schema_version": 4,
        "generator": "scripts/generate_u280_comparison_fixture.py",
        "dataset": args.dataset,
        "model": args.model,
        "model_id": model_id,
        "batch_size": args.batch_size,
        "num_events": num_events,
        "num_vertices": num_vertices,
        "num_targets": len(target_vertex),
        "history_entries": len(history_event_idx),
        "fanout": int(model["fanout"]),
        "depth": int(model["depth"]),
        "seed": seed,
        "input_kind": input_kind,
        "input_sha256": input_sha256,
        "input_source": source_metadata,
        "vertex_mapping": "first-occurrence compact IDs within the bounded sample",
        "timestamp_mapping": timestamp_mapping,
        "files_sha256": files,
        "tempgnn_golden": {
            "kernel_checksum": tempgnn_stats[11],
            "embedding_checksum": embedding_checksum(tempgnn_embedding),
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output.resolve())


def synthetic_events(dataset: str) -> tuple[list[int], list[int], list[int]]:
    num_events, num_vertices = SYNTHETIC_SHAPES[dataset]
    seed = DATASET_SEEDS[dataset]
    event_src: list[int] = []
    event_dst: list[int] = []
    for event_idx in range(num_events):
        src = (event_idx * 17 + seed + event_idx // 11) % num_vertices
        dst = (event_idx * 31 + seed * 3 + event_idx // 7) % num_vertices
        if dst == src:
            dst = (dst + 1) % num_vertices
        event_src.append(src)
        event_dst.append(dst)
    return event_src, event_dst, list(range(1, num_events + 1))


def load_real_events(
    path: Path,
) -> tuple[list[int], list[int], list[int], dict[str, object]]:
    raw_events: list[tuple[str, str, float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = {str(name).lower(): str(name) for name in (reader.fieldnames or [])}
        if not {"src", "dst", "time"}.issubset(fields):
            raise SystemExit(f"real sample must contain src,dst,time columns: {path}")
        for row in reader:
            timestamp = float(row[fields["time"]])
            if not math.isfinite(timestamp):
                raise SystemExit(f"real sample has a non-finite timestamp: {path}")
            raw_events.append((row[fields["src"]], row[fields["dst"]], timestamp))
            if len(raw_events) == MAX_EVENTS:
                break
    raw_events.sort(key=lambda event: event[2])
    if not raw_events:
        raise SystemExit(f"real sample has no events: {path}")
    vertex_ids: dict[str, int] = {}

    def compact(value: str) -> int:
        if value not in vertex_ids:
            vertex_ids[value] = len(vertex_ids)
        return vertex_ids[value]

    event_src = [compact(src) for src, _, _ in raw_events]
    event_dst = [compact(dst) for _, dst, _ in raw_events]
    source_times = [timestamp for _, _, timestamp in raw_events]
    positive_gaps = [
        later - earlier
        for earlier, later in zip(source_times, source_times[1:])
        if later > earlier
    ]
    units_per_tick = statistics.median(positive_gaps) if positive_gaps else 1.0
    span = source_times[-1] - source_times[0]
    max_tick = (1 << 32) - 1
    if span / units_per_tick >= max_tick - 1:
        units_per_tick = span / float(max_tick - 2)
    origin = source_times[0]
    event_ts = [
        min(max_tick, int(round((timestamp - origin) / units_per_tick)) + 1)
        for timestamp in source_times
    ]
    mapping = {
        "method": "relative_source_time_quantized_by_median_positive_gap",
        "origin": origin,
        "source_time_units_per_tick": units_per_tick,
        "first_tick": event_ts[0],
        "last_tick": event_ts[-1],
    }
    return event_src, event_dst, event_ts, mapping


def write_array(path: Path, typecode: str, values: list[int]) -> str:
    payload = array(typecode, values)
    if sys.byteorder != "little":
        payload.byteswap()
    data = payload.tobytes()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def embedding_checksum(values: list[int]) -> int:
    checksum = 1469598103934665603
    for value in values:
        checksum ^= value & 0xFFFF
        checksum = (checksum * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return checksum


if __name__ == "__main__":
    main()
