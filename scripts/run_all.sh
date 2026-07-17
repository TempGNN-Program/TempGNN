#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mode="${1:-default}"

setup_xrt() {
  if ! command -v xbutil >/dev/null 2>&1; then
    if [[ ! -f /opt/xilinx/xrt/setup.sh ]]; then
      echo "XRT is not configured and /opt/xilinx/xrt/setup.sh is unavailable" >&2
      exit 1
    fi
    # shellcheck disable=SC1091
    source /opt/xilinx/xrt/setup.sh
  fi
}

case "$mode" in
  default)
    make smoke
    make report
    ;;
  u280-core)
    setup_xrt
    make ae-core-u280
    ;;
  u280-core-strict)
    setup_xrt
    make ae-core-u280-strict
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
    echo "Usage: $0 [default|smoke|data|figures|q14|report|u280-core|u280-core-strict|u280-build|u280-run|u55c-run|package]" >&2
    exit 2
    ;;
esac
