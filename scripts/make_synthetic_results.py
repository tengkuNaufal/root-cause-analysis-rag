"""Buat file hasil run SINTETIS untuk menguji evaluator sebelum data pilot asli tersedia.

    python scripts/make_synthetic_results.py --pilot            # 3 fault x 3 varian x 1 trial
    python scripts/make_synthetic_results.py --trials 5          # 30 fault x 3 varian x 5 trial = 450

Setiap baris diberi "synthetic": true dan evaluator menampilkan peringatan.
Angka di sini BUKAN hasil eksperimen dan tidak boleh masuk laporan.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rca.catalog import load_catalog  # noqa: E402
from rca.linter import lint  # noqa: E402

VARIANTS = {  # p(benar), median waktu diagnosis (s)
    "zero_shot": (0.45, 2.5),
    "text_rag": (0.65, 3.6),
    "graph_rag": (0.80, 4.4),
}


def make_run(rng: random.Random, fault, catalog, variant: str, trial: int) -> dict:
    p_ok, t_med = VARIANTS[variant]
    available = [f"ev-{fault.id.lower()}-{i:02d}" for i in range(8)]
    correct = rng.random() < p_ok
    if correct:
        router, cls, commands = fault.router, fault.fault_class, fault.fix
    else:
        other = rng.choice([f for f in catalog.values() if f.id != fault.id])
        if rng.random() < 0.5:  # kelas salah, router benar
            router, cls = fault.router, other.fault_class
            commands = [{**blk, "router": fault.router} for blk in other.fix]
        else:  # tuduh router lain
            router, cls, commands = other.router, other.fault_class, other.fix
    used = rng.sample(available, k=3)
    if rng.random() < 0.06:
        used.append("ev-tidak-ada-01")
    lint_res = lint(commands)
    t_diag = round(rng.lognormvariate(0, 0.35) * t_med, 2)
    recovered = correct and lint_res["passed"] and rng.random() < 0.93
    t_rec = round(t_diag + rng.uniform(1.2, 4.5), 2) if recovered else None
    return {
        "run_id": f"{fault.id}-{variant}-{trial}", "fault_id": fault.id, "variant": variant, "trial": trial,
        "synthetic": True,
        "agent": {"router": router, "root_cause": cls,
                  "confidence": round(min(0.99, max(0.05, rng.gauss(0.8 if correct else 0.6, 0.12))), 2),
                  "evidence_ids": used, "commands": commands,
                  "explanation": f"Gejala pada {router} cocok dengan pola {cls}; lihat evidence {', '.join(used[:2])}."},
        "evidence_ids_available": available,
        "lint": lint_res,
        "applied": lint_res["passed"],
        "recovered": recovered,
        "reverted": not recovered,
        "t_diagnosis_s": t_diag,
        "t_recovery_s": t_rec,
        "error": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="3 fault x 3 varian x 1 trial")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--seed", type=int, default=8)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    catalog = load_catalog()
    faults = [catalog[i] for i in ("F01", "F13", "F25")] if args.pilot else list(catalog.values())
    trials = 1 if args.pilot else args.trials
    out = args.out or Path("results/runs") / ("pilot.synthetic.jsonl" if args.pilot else "full.synthetic.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for t in range(1, trials + 1):
            for fault in faults:
                for v in VARIANTS:
                    f.write(json.dumps(make_run(rng, fault, catalog, v, t), ensure_ascii=False) + "\n")
    print(f"{out}: {len(faults) * trials * len(VARIANTS)} run sintetis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
