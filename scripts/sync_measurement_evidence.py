from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


CHECKSUM_FIELDS = (
    "kernel_checksum",
    "embedding_checksum",
    "warmup_kernel_checksum",
    "warmup_embedding_checksum",
    "expected_kernel_checksum",
    "expected_embedding_checksum",
)

HOST_FIELD_MAP = {
    "kernel_checksum": "kernel_checksum",
    "embedding_checksum": "embedding_checksum",
    "warmup_kernel_checksum": "warmup_kernel_checksum",
    "warmup_embedding_checksum": "warmup_embedding_checksum",
    "expected_kernel_checksum": "expected_kernel_checksum",
    "expected_embedding_checksum": "expected_embedding_checksum",
    "kernel_iterations": "iterations",
    "batch_size": "num_targets",
    "repeat_consistency": "repeat_consistency",
    "golden_validation": "golden_validation",
}

ROW_KEY_FIELDS = ("dataset", "model", "repetition")


def main() -> None:
    args = parse_args()
    for system in args.systems:
        sync_system(args.run_dir, system)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize per-measurement evidence JSON files with a confirmed "
            "latest measurements.csv while preserving exact integer checksums."
        )
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--systems", nargs="+", required=True)
    return parser.parse_args()


def sync_system(run_dir: Path, system: str) -> None:
    raw_dir = run_dir / "raw" / system
    csv_path = raw_dir / "measurements.csv"
    evidence_dir = raw_dir / "measurements_evidence"
    rows = read_rows(csv_path)
    if not rows:
        raise SystemExit(f"{system}: no rows in {csv_path}")
    if not evidence_dir.is_dir():
        raise SystemExit(f"{system}: missing evidence directory {evidence_dir}")

    payloads: list[tuple[Path, dict[str, object], dict[str, str]]] = []
    seen: set[tuple[str, str, str]] = set()
    restored = 0
    for row in rows:
        key = row_key(row)
        if key in seen:
            raise SystemExit(f"{system}: duplicate measurement row {key}")
        seen.add(key)
        evidence_path = evidence_dir / evidence_filename(row)
        if not evidence_path.is_file():
            raise SystemExit(f"{system}: missing evidence file {evidence_path}")
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        old_row = payload.get("csv_row")
        host_values = payload.get("host_values")
        if not isinstance(old_row, dict) or not isinstance(host_values, dict):
            raise SystemExit(f"{system}: malformed evidence file {evidence_path}")

        normalized = dict(row)
        for field in CHECKSUM_FIELDS:
            if re.fullmatch(r"[0-9]+", normalized[field]):
                continue
            exact = host_values.get(field, old_row.get(field))
            if not isinstance(exact, str) or not re.fullmatch(r"[0-9]+", exact):
                raise SystemExit(
                    f"{system}: cannot restore exact {field} in {evidence_path}"
                )
            normalized[field] = exact
            restored += 1

        normalized["energy_mj"] = (
            f"{Decimal(normalized['latency_ms']) * Decimal(normalized['power_w']):.9f}"
        )
        payload["csv_row"] = {
            field: coerce_like(old_row.get(field), value)
            for field, value in normalized.items()
        }
        for csv_field, host_field in HOST_FIELD_MAP.items():
            host_values[host_field] = normalized[csv_field]
        host_values["kernel_time_ms"] = normalized["latency_ms"]
        host_values["validation"] = (
            "PASS"
            if normalized["golden_validation"] == "PASS"
            and normalized["repeat_consistency"] == "PASS"
            else "FAIL"
        )
        payload["host_values"] = host_values
        payload["evidence_sync"] = {
            "source": "measurements.csv",
            "row_key": {
                field: normalized[field] for field in ROW_KEY_FIELDS
            },
            "synchronized_utc": datetime.now(timezone.utc).isoformat(),
            "note": (
                "csv_row and directly mapped host fields were synchronized to "
                "the confirmed latest CSV; original command and power samples "
                "were retained."
            ),
        }
        payloads.append((evidence_path, payload, normalized))

    expected_files = {path for path, _, _ in payloads}
    actual_files = set(evidence_dir.glob("*.json"))
    if actual_files != expected_files:
        missing_rows = sorted(path.name for path in actual_files - expected_files)
        raise SystemExit(
            f"{system}: evidence files without CSV rows: {', '.join(missing_rows)}"
        )

    write_rows(csv_path, [row for _, _, row in payloads])
    csv_sha256 = sha256_file(csv_path)
    for evidence_path, payload, _ in payloads:
        sync = payload["evidence_sync"]
        assert isinstance(sync, dict)
        sync["source_csv_sha256"] = csv_sha256
        evidence_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(
        f"{system}: synchronized {len(rows)} rows and evidence files; "
        f"restored {restored} exact checksum fields; csv_sha256={csv_sha256}"
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def row_key(row: dict[str, str]) -> tuple[str, str, str]:
    return tuple(row[field] for field in ROW_KEY_FIELDS)  # type: ignore[return-value]


def evidence_filename(row: dict[str, str]) -> str:
    return f"{row['dataset']}_{row['model']}_r{int(Decimal(row['repetition']))}.json"


def coerce_like(old_value: object, new_value: str) -> object:
    if isinstance(old_value, int):
        return int(Decimal(new_value))
    if isinstance(old_value, float):
        return float(new_value)
    return new_value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
