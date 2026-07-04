#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mode="${1:-default}"

case "$mode" in
  default)
    make smoke
    make q14
    make report
    ;;
  smoke)
    make smoke
    ;;
  data)
    make data
    ;;
  figures)
    make figures
    ;;
  q14)
    make q14
    ;;
  report)
    make report
    ;;
  u280-build)
    make u280-build
    ;;
  u280-run)
    make u280-run
    ;;
  u55c-run)
    make u55c-run
    ;;
  package)
    make package
    ;;
  *)
    echo "Usage: $0 [default|smoke|data|figures|q14|report|u280-build|u280-run|u55c-run|package]" >&2
    exit 2
    ;;
esac
