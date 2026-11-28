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
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from rca.evaluation_inputs import ATTEMPT_POLICIES, checked_catalog, identity, select_attempts
from rca.evaluator import VARIANT_ORDER, _agent_view, _order, load_runs
from rca.rubric_evidence import bundle, canonical, digest

DIMENSIONS = ["grounding", "kausal", "konsistensi", "perbaikan", "kejelasan"]


def sample(results: Path, out: Path, raters: list[str], seed: int, overlap: int, *,
           catalog_path: Path | None = None, attempt_policy: str = "reject",
           evidence_root: Path | None = None, variants: list[str] | None = None) -> None:
    if not raters or len(set(raters)) != len(raters) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", n) for n in raters):
        raise ValueError("Rater names must be unique safe filenames")
    if overlap < 0:
        raise ValueError("overlap must be nonnegative")
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Sample output must be empty; existing ratings will not be overwritten")
    raw = results.read_bytes()
    runs = load_runs(results)
    catalog, catalog_sha = checked_catalog(runs, catalog_path)
    runs, selection = select_attempts(runs, attempt_policy)
    variants = VARIANT_ORDER[:3] if variants is None else variants
    if not variants or not set(variants) <= set(VARIANT_ORDER):
        raise ValueError("Unknown or empty variant scope")
    selection.update(source_sha256=digest(raw), catalog_sha256=catalog_sha, seed=seed,
                     included_variants=variants)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in runs:
        if r["variant"] in variants:
            groups[(str(r["fault_id"]), r["variant"])].append(r)
    if not groups:
        raise ValueError("No runs in requested rubric scope")
    rng = random.Random(seed)
    picked = [rng.choice(sorted(groups[k], key=lambda r: r["trial"])) for k in sorted(groups)]
    rng.shuffle(picked)

    key_rows, items, bundles = [], [], {}
    for i, r in enumerate(picked, start=1):
        item_id = f"X{i:03d}"
        gt = catalog.get(str(r["fault_id"]))
        if gt is None:
            raise ValueError(f"Unknown catalog fault: {r['fault_id']}")
        agent = _agent_view(r)
        fragments, hashes = bundle(r, agent["evidence_ids"], evidence_root)
        packet = canonical({"item_id": item_id, "evidence": fragments}) + "\n"
        bundles[item_id] = packet
        diag = r.get("diagnosis") or {}
        ids = identity(r)
        ids["request_id"] = ids["request_id"] or diag.get("request_id")
        ids["job_id"] = ids["job_id"] or diag.get("job_id")
        ids["run_id"] = ids["run_id"] or ids["request_id"] or digest(canonical(r).encode())
        key_rows.append({"item_id": item_id, **ids,
                         "source_sha256": selection["source_sha256"], "catalog_sha256": catalog_sha,
                         "row_sha256": digest(canonical(r).encode()),
                         "bundle_sha256": digest(packet.encode()), "evidence_hashes": canonical(hashes)})
        items.append({
            "item_id": item_id,
            "gt_router": gt.router if gt else "", "gt_class": gt.fault_class if gt else "",
            "pred_router": agent["router"] or "", "pred_root_cause": agent["root_cause"] or "",
            "evidence_ids": " ".join(agent.get("evidence_ids") or []),
            "evidence_bundle": f"evidence/{item_id}.json",
            "commands": json.dumps(agent.get("commands") or [], ensure_ascii=False),
            "explanation": agent["explanation"] or "",
            **{d: "" for d in DIMENSIONS}, "catatan": "",
        })
    # No output is written until all selected sources/hashes have been verified.
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence").mkdir()
    for item_id, packet in bundles.items():
        (out / "evidence" / f"{item_id}.json").write_text(packet, encoding="utf-8")
    overlap = min(overlap, len(items))
    selection.update(sampled_items=len(items), overlap=overlap)
    (out / "selection.json").write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
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
    s.add_argument("--catalog", type=Path)
    s.add_argument("--attempt-policy", choices=ATTEMPT_POLICIES, default="reject")
    s.add_argument("--evidence-root", type=Path, help="arsip lokal <job_id>/evidence-index.json dan sumber JSON")
    s.add_argument("--variants", nargs="+", choices=VARIANT_ORDER, default=VARIANT_ORDER[:3])
    a = sub.add_parser("aggregate")
    a.add_argument("folder", type=Path, nargs="?", default=Path("results/explain"))
    args = ap.parse_args(argv)
    if args.cmd == "sample":
        sample(args.results, args.out, args.raters, args.seed, args.overlap,
               catalog_path=args.catalog, attempt_policy=args.attempt_policy,
               evidence_root=args.evidence_root, variants=args.variants)
    else:
        aggregate(args.folder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
