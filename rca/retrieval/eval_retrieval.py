"""Ukur kualitas retrieval: berapa pertanyaan yang jawabannya muncul di 5 hasil teratas.

    python -m rca.retrieval.eval_retrieval                 # semua konfigurasi
    python -m rca.retrieval.eval_retrieval --corpus <dir>  # korpus retriever kelompok

Keluaran di results/retrieval/: summary.csv, summary.md, per_question.csv
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from pathlib import Path

import yaml

from rca.retrieval.retriever import CORPUS, Retriever, RetrieverConfig

ROOT = Path(__file__).resolve().parents[2]
TESTSET = ROOT / "data" / "retrieval_testset.yaml"
OUT = ROOT / "results" / "retrieval"


def configs(base_dirs: list[Path], extra_dirs: list[Path]) -> list[RetrieverConfig]:
    """Perbaikan dicoba satu per satu terhadap baseline, lalu digabung bertahap."""
    b = RetrieverConfig(name="baseline", corpus_dirs=base_dirs, chunk_size=2000, overlap=0)
    small = dict(chunk_size=400, overlap=80)
    extra = dict(corpus_dirs=base_dirs + extra_dirs)
    return [
        b,
        replace(b, name="+chunk kecil", **small),
        replace(b, name="+dok FRR tambahan", **extra),
        replace(b, name="+terjemah ID->EN", translate=True),
        replace(b, name="+buang rincian", strip_details=True),
        replace(b, name="chunk kecil + dok tambahan", **small, **extra),
        replace(b, name="chunk kecil + dok + terjemah", **small, **extra, translate=True),
        replace(b, name="chunk kecil + semua", **small, **extra, translate=True, strip_details=True),
        replace(b, name="dok + terjemah", **extra, translate=True),
        replace(b, name="dok + terjemah + buang rincian", **extra, translate=True, strip_details=True),
        replace(b, name="chunk 800 + dok + terjemah + buang", **extra, chunk_size=800, overlap=120,
                translate=True, strip_details=True),
    ]


def load_testset(path: Path = TESTSET) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rel = data.get("relevance", {})
    items = []
    for q in data["questions"]:
        groups = q.get("relevant") or rel[q["class"]]
        for lang in ("id", "en"):
            items.append({"fault_id": q["fault_id"], "class": q["class"], "lang": lang,
                          "question": q[lang], "relevant": groups})
    return items


def is_relevant(text: str, groups: list[list[str]]) -> bool:
    t = text.lower()
    return any(all(term in t for term in g) for g in groups)


def evaluate(cfg: RetrieverConfig, items: list[dict], k: int = 5) -> tuple[dict, list[dict]]:
    r = Retriever(cfg)
    rows = []
    for it in items:
        hits = r.search(it["question"], k=k)
        rank = next((i + 1 for i, h in enumerate(hits) if is_relevant(h["text"], it["relevant"])), None)
        rows.append({**{x: it[x] for x in ("fault_id", "class", "lang")}, "config": cfg.name, "rank": rank or "",
                     "query": r.query_text(it["question"]), "top1": hits[0]["id"] if hits else ""})

    def agg(sub):
        n = len(sub)
        hit = sum(1 for x in sub if x["rank"])
        mrr = sum(1 / x["rank"] for x in sub if x["rank"]) / n if n else 0
        return hit, n, mrr

    summary = {"config": cfg.name, "chunks": r.collection.count()}
    for lang in ("id", "en", "all"):
        sub = [x for x in rows if lang == "all" or x["lang"] == lang]
        hit, n, mrr = agg(sub)
        summary[f"hit@{k}_{lang}"] = hit
        summary[f"n_{lang}"] = n
        summary[f"mrr_{lang}"] = round(mrr, 3)
    return summary, rows


def write_outputs(summaries: list[dict], rows: list[dict], out: Path, k: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0]))
        w.writeheader()
        w.writerows(summaries)
    with open(out / "per_question.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    base = summaries[0][f"hit@{k}_all"]
    lines = [f"| Konfigurasi | Chunk | Hit@{k} ID | Hit@{k} EN | Hit@{k} total | MRR total | Δ vs baseline |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for s in summaries:
        def pct(lang):
            return f"{s[f'hit@{k}_{lang}']}/{s[f'n_{lang}']} ({100 * s[f'hit@{k}_{lang}'] / s[f'n_{lang}']:.0f}%)"
        d = s[f"hit@{k}_all"] - base
        lines.append(f"| {s['config']} | {s['chunks']} | {pct('id')} | {pct('en')} | {pct('all')} | "
                     f"{s['mrr_all']:.3f} | {'+' if d > 0 else ''}{d} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, action="append", help="direktori korpus dasar (boleh berulang)")
    ap.add_argument("--extra", type=Path, action="append", help="direktori dokumentasi tambahan")
    ap.add_argument("--testset", type=Path, default=TESTSET)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args(argv)
    items = load_testset(args.testset)
    summaries, rows = [], []
    for cfg in configs(args.corpus or [CORPUS / "base"], args.extra or [CORPUS / "extra"]):
        s, r = evaluate(cfg, items, args.k)
        summaries.append(s)
        rows.extend(r)
        print(f"{cfg.name:32s} hit@{args.k} id={s[f'hit@{args.k}_id']:2d}/{s['n_id']} "
              f"en={s[f'hit@{args.k}_en']:2d}/{s['n_en']} total={s[f'hit@{args.k}_all']:2d}/{s['n_all']} "
              f"mrr={s['mrr_all']:.3f}")
    write_outputs(summaries, rows, args.out, args.k)
    print(f"\nTabel: {args.out / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
