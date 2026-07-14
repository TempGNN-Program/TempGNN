#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_u280_core_reproduction import load_config, preflight


PLACEHOLDER_MARKERS = ("REPLACE_", "TO_BE_FILLED", "zenodo.REPLACE_ME")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether pap142 is ready for a frozen Zenodo release.")
    parser.add_argument("--config", type=Path, default=Path("configs/u280_core_reproduction.json"))
    parser.add_argument("--runs", type=Path, default=Path("results/reviewer_u280_runs"))
    parser.add_argument("--require-clean-git", action="store_true")
    parser.add_argument(
        "--require-results-reproduced",
        action="store_true",
        help="also require paper-equivalent scope and passing paper-figure tolerances",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    warnings: list[str] = []
    required = [
        repo_root / "LICENSE",
        repo_root / "CITATION.cff",
        repo_root / ".zenodo.json",
        repo_root / args.config,
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing required release file: {path.relative_to(repo_root)}")

    for path in (repo_root / "CITATION.cff", repo_root / ".zenodo.json"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for marker in PLACEHOLDER_MARKERS:
                if marker in text:
                    errors.append(f"placeholder {marker!r} remains in {path.name}")

    config_path = repo_root / args.config
    if config_path.is_file():
        try:
            config = load_config(config_path)
            preflight(config, repo_root)
            if not bool(config.get("results_reproduced_eligible", False)):
                message = (
                    "current U280 comparison is explicitly not paper-equivalent; "
                    "Results Reproduced release claim is disabled"
                )
                (errors if args.require_results_reproduced else warnings).append(message)
        except SystemExit as exc:
            errors.append(f"U280 preflight failed: {exc}")

    runs_root = repo_root / args.runs
    complete_runs = []
    passing_runs = []
    if runs_root.is_dir():
        for verification in runs_root.glob("*/verification.json"):
            checks = json.loads(verification.read_text(encoding="utf-8"))
            if checks and (verification.parent / "provenance.json").is_file():
                complete_runs.append(verification.parent)
                if all(bool(result.get("pass")) for result in checks.values()):
                    passing_runs.append(verification.parent)
    if not complete_runs:
        errors.append("no complete fresh U280 reviewer run was found")
    if args.require_results_reproduced and not passing_runs:
        errors.append("no fresh U280 run passed the paper-figure tolerance checks")

    if args.require_clean_git:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, text=True
        ).strip()
        if status:
            errors.append("Git worktree is not clean")

    if errors:
        print("Zenodo release preflight FAIL")
        for warning in warnings:
            print(f"- warning: {warning}")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    latest = max(
        passing_runs if args.require_results_reproduced else complete_runs,
        key=lambda path: path.stat().st_mtime,
    )
    print("Zenodo release preflight PASS")
    for warning in warnings:
        print(f"- warning: {warning}")
    print(f"Fresh U280 evidence: {latest.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
