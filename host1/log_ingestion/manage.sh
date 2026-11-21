#!/usr/bin/env bash
# No router deploy/removal or global Docker operations.
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$PWD"
IMAGE=$(cat host1/log_ingestion/image.txt)
NAME=rca-vector
case "${1:-}" in
  prepare)
    for n in r1 r2 r3 r4 r5 r6; do
      mkdir -p "data/host1/logs/raw/$n"
      chown 100:101 "data/host1/logs/raw/$n"
      chmod 775 "data/host1/logs/raw/$n"
    done
    mkdir -p data/host1/logs/normalized data/host1/logs/vector-data
    ;;
  validate|test|start)
    for p in data/host1/logs/raw/r1 data/host1/logs/normalized data/host1/logs/vector-data; do
      test -d "$p" || { echo 'Run prepare first'; exit 1; }
    done
    mounts=(--mount "type=bind,src=$ROOT/host1/log_ingestion/vector.yaml,dst=/etc/vector/vector.yaml,readonly"
      --mount "type=bind,src=$ROOT/data/host1/logs/raw,dst=/frr,readonly"
      --mount "type=bind,src=$ROOT/data/host1/logs/normalized,dst=/logs"
      --mount "type=bind,src=$ROOT/data/host1/logs/vector-data,dst=/var/lib/vector")
    security=(--network none --read-only --cap-drop ALL --security-opt no-new-privileges)
    if [[ $1 == start ]]; then
      docker run -d --name "$NAME" --label project=rca --restart no "${security[@]}" "${mounts[@]}" "$IMAGE" --config /etc/vector/vector.yaml
    else
      docker run --rm "${security[@]}" "${mounts[@]}" "$IMAGE" "$1" /etc/vector/vector.yaml
    fi
    ;;
  status) docker inspect --format '{{.Name}} {{json .State}}' "$NAME" ;;
  *) echo 'Usage: bash host1/log_ingestion/manage.sh prepare|validate|test|start|status'; exit 2 ;;
esac
