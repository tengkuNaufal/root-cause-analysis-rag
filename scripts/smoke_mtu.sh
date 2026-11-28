#!/usr/bin/env bash
# Smoke test MTU: tiga fault mtu_mismatch (F01-F03) dijalankan lengkap dengan --execute, lalu tiap run
# dinilai terhadap target pemulihan di bawah 10 detik sejak gejala terdeteksi.
#
#   bash scripts/smoke_mtu.sh graph_rag      # agen live, butuh API Host 1
#   bash scripts/smoke_mtu.sh rule_based     # pembanding regex, tanpa API
set -uo pipefail
cd "$(dirname "$0")/.."

variant=${1:-graph_rag}
target=${SMOKE_TARGET:-10}
api=${DEMO_API:-http://127.0.0.1:8766}
case $variant in
    zero_shot | text_rag | graph_rag | rule_based) ;;
    *) echo "Varian gak dikenal: $variant"; exit 2 ;;
esac

api_args=()
if [ "$variant" != rule_based ]; then
    # Memakai token sesi live server Host 1 kalau ada, selain itu diminta interaktif biar gak masuk history.
    session=$(cat private/live-agent/latest.txt 2>/dev/null)
    if [ -z "${LIVE_API_TOKEN:-}" ] && [ -n "$session" ] && [ -r "$session/token.txt" ]; then
        LIVE_API_TOKEN=$(cat "$session/token.txt")
    fi
    if [ -z "${LIVE_API_TOKEN:-}" ]; then
        read -rsp 'Token API: ' LIVE_API_TOKEN
        echo
    fi
    export LIVE_API_TOKEN
    api_args=(--api "$api")
fi

out="data/host2/smoke-mtu/$(date -u +%Y%m%dT%H%M%SZ)-$variant"
python3 scripts/bench.py "${api_args[@]}" --out "$out" --execute --faults F01,F02,F03 --variants "$variant" \
    --trials 1 || exit $?
echo
python3 scripts/bench_status.py "$out" --target "$target"
