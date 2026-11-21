#!/usr/bin/env bash
# Run in NetworkLab: sudo bash lab/host1/frr/validate-config.sh
# Creates only short-lived, network-isolated parser containers, not a lab.
set -euo pipefail
topology_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd -- "$topology_dir/../../.." && pwd)
result_dir="$project_dir/data/host1/frr-config/$(date +%Y%m%dT%H%M%S)-validation"
mkdir -p "$result_dir"
image=$(sed -n 's/^    image: //p' "$topology_dir/topology.clab.yml")
test -n "$image"
docker image inspect "$image" > /dev/null
clab validate -t "$topology_dir/topology.clab.yml" 2>&1 | tee "$result_dir/topology.log"
for node in r1 r2 r3 r4 r5 r6; do
  log="$result_dir/$node.log"
  if ! docker run --rm --network none \
    --mount "type=bind,src=$topology_dir/configs/$node/frr.conf,dst=/etc/frr/frr.conf,readonly" \
    --mount "type=bind,src=$topology_dir/validation/vtysh.conf,dst=/etc/frr/vtysh.conf,readonly" \
    --entrypoint vtysh "$image" -C > "$log" 2>&1; then
    cat "$log"
    echo "FAIL: $node parser exited nonzero" | tee -a "$result_dir/summary.log"
    exit 1
  fi
  # vtysh can return zero on file-processing errors: never rely only on exit code.
  if grep -Eiq 'unknown command|ambiguous command|incomplete command|processing failure|can.t open|error|failed|invalid' "$log"; then
    cat "$log"
    echo "FAIL: $node parser reported an error" | tee -a "$result_dir/summary.log"
    exit 1
  fi
  cat "$log"
  echo "PASS: $node FRR syntax dry-run" | tee -a "$result_dir/summary.log"
done
echo "PASS: topology and six configs. Routing/runtime NOT tested. Evidence: $result_dir" | tee -a "$result_dir/summary.log"
