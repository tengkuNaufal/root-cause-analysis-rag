"""Sampling dan agregasi penilaian explainability (rubrik: docs/rubrik-explainability.md).

1) Ambil sampel acak: satu trial per fault per varian (30 x 3 = 90 penjelasan), varian
   disembunyikan (blind), dibagi rata ke tiga anggota. Sejumlah item `--overlap` dinilai
   oleh semua anggota untuk mengukur kesepakatan antarpenilai.

    python -m rca.explain sample results/runs/full.jsonl --raters ashkar fayyaz naufal

2) Setelah setiap anggota mengisi kolom skor di CSV miliknya:

    python -m rca.explain aggregate results/explain
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from rca.catalog import load_catalog
from rca.evaluator import _order, load_runs

DIMENSIONS = ["grounding", "kausal", "konsistensi", "perbaikan", "kejelasan"]


def sample(results: Path, out: Path, raters: list[str], seed: int, overlap: int) -> None:
    catalog = load_catalog()
    runs = load_runs(results)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in runs:
        groups[(str(r["fault_id"]), r["variant"])].append(r)
    rng = random.Random(seed)
    picked = [rng.choice(sorted(groups[k], key=lambda r: str(r.get("trial")))) for k in sorted(groups)]
    rng.shuffle(picked)

    out.mkdir(parents=True, exist_ok=True)
    key_rows, items = [], []
    for i, r in enumerate(picked, start=1):
        item_id = f"X{i:03d}"
        gt = catalog.get(str(r["fault_id"]))
        agent = r.get("agent") or {}
        key_rows.append({"item_id": item_id, "run_id": r.get("run_id"), "fault_id": r["fault_id"],
                         "variant": r["variant"], "trial": r.get("trial")})
        items.append({
            "item_id": item_id,
            "gt_router": gt.router if gt else "", "gt_class": gt.fault_class if gt else "",
            "pred_router": agent.get("router", ""), "pred_root_cause": agent.get("root_cause", ""),
            "evidence_ids": " ".join(agent.get("evidence_ids") or []),
            "commands": json.dumps(agent.get("commands") or [], ensure_ascii=False),
            "explanation": agent.get("explanation", ""),
            **{d: "" for d in DIMENSIONS}, "catatan": "",
        })
    shared = items[:overlap]
    rest = items[overlap:]
    for n, name in enumerate(raters):
        mine = shared + rest[n::len(raters)]
        with open(out / f"penilaian_{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(items[0]))
            w.writeheader()
            w.writerows(sorted(mine, key=lambda x: x["item_id"]))
    with open(out / "kunci_sampel.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(key_rows[0]))
        w.writeheader()
        w.writerows(key_rows)
    print(f"{len(items)} penjelasan, {overlap} dinilai semua anggota; file di {out}")
    print("Jangan buka kunci_sampel.csv sebelum penilaian selesai (varian disembunyikan).")


def aggregate(folder: Path) -> None:
    key = {r["item_id"]: r for r in csv.DictReader(open(folder / "kunci_sampel.csv", encoding="utf-8"))}
    scores: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    per_rater: dict[str, dict[str, int]] = {}
    missing = 0
    for path in sorted(folder.glob("penilaian_*.csv")):
        rater = path.stem.removeprefix("penilaian_")
        per_rater[rater] = {}
        for row in csv.DictReader(open(path, encoding="utf-8-sig")):
            vals = []
            for d in DIMENSIONS:
                v = (row.get(d) or "").strip()
                if v not in {"0", "1", "2"}:
                    missing += 1
                    break
                vals.append(int(v))
            else:
                for d, v in zip(DIMENSIONS, vals):
                    scores[row["item_id"]][d].append(v)
                per_rater[rater][row["item_id"]] = sum(vals)
    if missing:
        print(f"Peringatan: {missing} baris belum lengkap (skor harus 0, 1, atau 2) dan dilewati.")

    by_variant: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for item, dims in scores.items():
        v = key[item]["variant"]
        for d in DIMENSIONS:
            by_variant[v][d].append(sum(dims[d]) / len(dims[d]))
        by_variant[v]["total"].append(sum(sum(dims[d]) / len(dims[d]) for d in DIMENSIONS))

    cols = DIMENSIONS + ["total"]
    lines = ["| Varian | n | " + " | ".join(c.capitalize() for c in DIMENSIONS) + " | Total (0-10) |",
             "|---|---:|" + "---:|" * len(cols)]
    rows = []
    for v in _order(by_variant):
        means = {c: sum(by_variant[v][c]) / len(by_variant[v][c]) for c in cols}
        rows.append({"variant": v, "n": len(by_variant[v]["total"]), **means})
        lines.append(f"| {v} | {rows[-1]['n']} | " + " | ".join(f"{means[c]:.2f}" for c in cols) + " |")

    # kesepakatan antarpenilai pada item bersama (selisih skor total)
    agree = []
    for a, b in combinations(per_rater, 2):
        common = set(per_rater[a]) & set(per_rater[b])
        for it in common:
            agree.append(abs(per_rater[a][it] - per_rater[b][it]))
    if agree:
        lines += ["", f"Kesepakatan antarpenilai: {len(agree)} pasangan penilaian pada item bersama, "
                      f"rata-rata selisih skor total {sum(agree) / len(agree):.2f} dari 10, "
                      f"{100 * sum(x <= 1 for x in agree) / len(agree):.0f}% berselisih <= 1 poin."]
    (folder / "ringkasan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(folder / "ringkasan.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["variant", "n"] + cols)
        w.writeheader()
        w.writerows(rows)
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("results", type=Path)
    s.add_argument("--out", type=Path, default=Path("results/explain"))
    s.add_argument("--raters", nargs="+", default=["ashkar", "fayyaz", "naufal"])
    s.add_argument("--seed", type=int, default=2026)
    s.add_argument("--overlap", type=int, default=9)
    a = sub.add_parser("aggregate")
    a.add_argument("folder", type=Path, nargs="?", default=Path("results/explain"))
    args = ap.parse_args(argv)
    if args.cmd == "sample":
        sample(args.results, args.out, args.raters, args.seed, args.overlap)
    else:
        aggregate(args.folder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
