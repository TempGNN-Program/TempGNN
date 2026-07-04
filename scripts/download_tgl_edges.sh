#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="https://s3.us-west-2.amazonaws.com/dgl-data/dataset/tgl"

if [ "$#" -eq 0 ]; then
  set -- WIKI MOOC REDDIT
fi

expected_min_bytes() {
  case "$1" in
    WIKI) echo 5000000 ;;
    MOOC) echo 13000000 ;;
    REDDIT) echo 25000000 ;;
    LASTFM) echo 45000000 ;;
    MAG) echo 40000000000 ;;
    GDELT) echo 7000000000 ;;
    *) echo 1 ;;
  esac
}

download_one() {
  local dataset="$1"
  local out_dir="$ROOT_DIR/external/tgl/DATA/$dataset"
  local out_file="$out_dir/edges.csv"
  local url="$BASE_URL/$dataset/edges.csv"
  local min_bytes
  min_bytes="$(expected_min_bytes "$dataset")"

  mkdir -p "$out_dir"
  if [ -s "$out_file" ]; then
    local size
    size="$(stat -c%s "$out_file" 2>/dev/null || wc -c < "$out_file")"
    if [ "$size" -ge "$min_bytes" ]; then
      echo "[$dataset] edges.csv exists ($size bytes), skipping"
      return
    fi
    echo "[$dataset] existing file is too small ($size bytes), resuming download"
  fi

  echo "[$dataset] downloading $url"
  if command -v wget >/dev/null 2>&1; then
    (cd "$out_dir" && wget -c -t 8 --timeout=60 --waitretry=3 --progress=dot:giga "$url")
  elif command -v curl >/dev/null 2>&1; then
    curl -L --retry 8 --retry-delay 3 --connect-timeout 30 -C - -o "$out_file" "$url"
  else
    echo "Neither wget nor curl is available" >&2
    exit 1
  fi

  local final_size
  final_size="$(stat -c%s "$out_file" 2>/dev/null || wc -c < "$out_file")"
  if [ "$final_size" -lt "$min_bytes" ]; then
    echo "[$dataset] downloaded file is unexpectedly small: $final_size bytes" >&2
    exit 1
  fi
  head -1 "$out_file"
  echo "[$dataset] ready: $out_file ($final_size bytes)"
}

for dataset in "$@"; do
  download_one "$dataset"
done
