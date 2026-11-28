#!/usr/bin/env bash
# Menjalankan satu run live buat demo: inject fault, diagnosis agen, lint, perbaikan, verifikasi,
# lalu nampilin detail run-nya. Dijalankan di WSL host utama, bisa juga dipanggil dari laptop lewat lab.ps1.
#
#   bash scripts/demo.sh F01 graph_rag
set -uo pipefail
cd "$(dirname "$0")/.."

fault=${1:-}
variant=${2:-graph_rag}
api=${DEMO_API:-http://127.0.0.1:8766}
python=${HOST1_PYTHON:-private/.venv-retriever-wsl/bin/python}
if [ ! -x "$python" ]; then python=python3; fi
export PYTHONPATH="$PWD/host1:$PWD:$PWD/private/live-agent-deps${PYTHONPATH:+:$PYTHONPATH}"
[[ $fault =~ ^F[0-9]{2}$ ]] || { echo "Pakai: bash scripts/demo.sh F01 [graph_rag|text_rag|zero_shot]"; exit 2; }
case $variant in zero_shot | text_rag | graph_rag) ;; *) echo "Varian gak dikenal: $variant"; exit 2 ;; esac

# Meminta token interaktif kalau belum ada di environment, biar gak pernah ketulis ke file atau history.
if [ -z "${LIVE_API_TOKEN:-}" ]; then
    read -rsp 'Token API: ' LIVE_API_TOKEN
    echo
    export LIVE_API_TOKEN
fi

out="data/host2/demo/$(date -u +%Y%m%dT%H%M%SZ)-$fault-$variant"
rc=0
"$python" scripts/bench.py --api "$api" --out "$out" --execute --faults "$fault" --variants "$variant" --trials 1 || rc=$?
if [ -s "$out/results.jsonl" ]; then
    echo
    "$python" scripts/bench_status.py "$out" --show last
fi
exit $rc
