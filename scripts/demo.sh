#!/usr/bin/env bash
# Menjalankan satu run live buat demo: inject fault, diagnosis agen, lint, perbaikan, verifikasi,
# lalu nampilin detail run-nya. Dijalankan di WSL host utama, bisa juga dipanggil dari laptop lewat lab.ps1.
#
#   bash scripts/demo.sh F01 graph_rag
#   bash scripts/demo.sh F01 rule_based      # pembanding regex, tanpa API
set -uo pipefail
cd "$(dirname "$0")/.."

fault=${1:-}
variant=${2:-graph_rag}
api=${DEMO_API:-http://127.0.0.1:8766}
if [[ ! $fault =~ ^F[0-9]{2}$ ]]; then
    echo "Pakai: bash scripts/demo.sh F01 [graph_rag|text_rag|zero_shot|rule_based]"
    exit 2
fi
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

out="data/host2/demo/$(date -u +%Y%m%dT%H%M%SZ)-$fault-$variant"
rc=0
python3 scripts/bench.py "${api_args[@]}" --out "$out" --execute --faults "$fault" --variants "$variant" \
    --trials 1 || rc=$?
if [ -s "$out/results.jsonl" ]; then
    echo
    python3 scripts/bench_status.py "$out" --show last
fi
exit $rc
