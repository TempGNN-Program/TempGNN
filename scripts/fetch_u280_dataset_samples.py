#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import urllib.request
from pathlib import Path
from typing import Iterator, TextIO


DATASETS = {
    "WK": {
        "name": "Wikipedia",
        "url": "https://s3.us-west-2.amazonaws.com/dgl-data/dataset/tgl/WIKI/edges.csv",
        "format": "csv",
        "citation_url": "https://github.com/amazon-science/tgl",
    },
    "MC": {
        "name": "MOOC",
        "url": "https://s3.us-west-2.amazonaws.com/dgl-data/dataset/tgl/MOOC/edges.csv",
        "format": "csv",
        "citation_url": "https://snap.stanford.edu/data/act-mooc.html",
    },
    "RT": {
        "name": "Reddit",
        "url": "https://s3.us-west-2.amazonaws.com/dgl-data/dataset/tgl/REDDIT/edges.csv",
        "format": "csv",
        "citation_url": "https://github.com/amazon-science/tgl",
    },
    "LM": {
        "name": "LastFM",
        "url": "https://s3.us-west-2.amazonaws.com/dgl-data/dataset/tgl/LASTFM/edges.csv",
        "format": "csv",
        "citation_url": "https://github.com/amazon-science/tgl",
    },
    "WT": {
        "name": "WikiTalk",
        "url": "https://snap.stanford.edu/data/wiki-talk-temporal.txt.gz",
        "format": "snap_gzip",
        "citation_url": "https://snap.stanford.edu/data/",
    },
    "GT": {
        "name": "GDELT",
        "url": "https://s3.us-west-2.amazonaws.com/dgl-data/dataset/tgl/GDELT/edges.csv",
        "format": "csv",
        "citation_url": "https://github.com/amazon-science/tgl",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch deterministic real-dataset prefixes for the bounded U280 forward path."
    )
    parser.add_argument("--datasets", nargs="+", choices=DATASETS, default=list(DATASETS))
    parser.add_argument(
        "--output-root", type=Path, default=Path("external/u280_dataset_samples")
    )
    parser.add_argument("--events", type=int, default=8192)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.events < 1000 or args.events > 8192:
        raise SystemExit("events must be in 1000..8192 for the packaged forward kernel")
    for alias in args.datasets:
        fetch_dataset(alias, args.output_root, args.events, force=args.force)


def fetch_dataset(alias: str, output_root: Path, events: int, *, force: bool) -> Path:
    config = DATASETS[alias]
    output_dir = output_root / alias
    output_path = output_dir / "edges.csv"
    metadata_path = output_dir / "metadata.json"
    if output_path.is_file() and metadata_path.is_file() and not force:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("schema_version") == 1
            and metadata.get("dataset") == alias
            and metadata.get("sample_events") == events
            and metadata.get("sample_sha256") == sha256_file(output_path)
        ):
            print(f"{alias}: reused {events}-event real-data sample")
            return output_path

    request = urllib.request.Request(
        str(config["url"]),
        headers={"User-Agent": "TempGNN-SC26-AE/1.0", "Accept-Encoding": "identity"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        stream: TextIO
        if config["format"] == "snap_gzip":
            stream = io.TextIOWrapper(gzip.GzipFile(fileobj=response), encoding="utf-8")
        else:
            stream = io.TextIOWrapper(response, encoding="utf-8")
        rows = list(read_rows(stream, str(config["format"]), events))
    if len(rows) != events:
        raise SystemExit(f"{alias}: expected {events} source rows, received {len(rows)}")

    timestamps = [float(row["time"]) for row in rows]
    if not all(math.isfinite(timestamp) for timestamp in timestamps):
        raise SystemExit(f"{alias}: source contains a non-finite timestamp")
    source_order_was_monotonic = all(
        earlier <= later for earlier, later in zip(timestamps, timestamps[1:])
    )
    rows.sort(key=lambda row: float(row["time"]))

    output_dir.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["src", "dst", "time"])
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "schema_version": 1,
        "dataset": alias,
        "dataset_name": config["name"],
        "input_kind": "real_dataset_prefix",
        "source_url": config["url"],
        "citation_url": config["citation_url"],
        "selection": "first source records, sorted chronologically within the selected prefix",
        "source_order_was_monotonic": source_order_was_monotonic,
        "sample_events": events,
        "sample_sha256": sha256_file(output_path),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"{alias}: wrote {events}-event real-data sample")
    return output_path


def read_rows(stream: TextIO, source_format: str, limit: int) -> Iterator[dict[str, str]]:
    if source_format == "csv":
        reader = csv.DictReader(stream)
        fields = {str(name).lower(): str(name) for name in (reader.fieldnames or [])}
        try:
            src_key = fields["src"]
            dst_key = fields["dst"]
            time_key = fields["time"]
        except KeyError as exc:
            raise SystemExit(f"dataset CSV lacks src/dst/time columns: {reader.fieldnames}") from exc
        for row in reader:
            yield {"src": row[src_key], "dst": row[dst_key], "time": row[time_key]}
            limit -= 1
            if limit == 0:
                return
        return

    emitted = 0
    for line in stream:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) < 3:
            continue
        yield {"src": fields[0], "dst": fields[1], "time": fields[2]}
        emitted += 1
        if emitted == limit:
            return


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
