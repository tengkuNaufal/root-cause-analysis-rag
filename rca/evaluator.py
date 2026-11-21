"""Evaluator: membaca file hasil run (JSON Lines) dan katalog, lalu menghitung metrik per varian.

    python -m rca.evaluator results/runs/pilot.jsonl --out results/eval/pilot

Satu baris hasil run (usulan kontrak dengan runner; nama field alternatif juga diterima):
{
  "run_id": "F01-text_rag-1", "fault_id": "F01", "variant": "text_rag", "trial": 1,
  "agent": {"router": "r1", "root_cause": "mtu_mismatch", "confidence": 0.86,
            "evidence_ids": ["ev-..."], "commands": [{"router": "r1", "commands": ["..."]}],
            "explanation": "..."},
  "evidence_ids_available": ["ev-...", ...],   # ID evidence yang benar-benar dikirim ke agen
  "lint": {"passed": true, "violations": []},
  "applied": true, "recovered": true, "reverted": false,
  "t_diagnosis_s": 4.2,     # gejala terdeteksi -> jawaban agen keluar
  "t_recovery_s": 7.9,      # gejala terdeteksi -> jaringan terverifikasi pulih (null jika tidak pulih)
  "error": null
}

Metrik per varian:
  rca_accuracy        router DAN kelas akar masalah cocok dengan ground truth katalog
  command_correctness perintah lolos linter DAN jaringan pulih (dibagi semua run)
  fix_success_rate    jaringan pulih di antara run yang perintahnya dijalankan
  t_diagnosis median / p90, t_recovery median / p90 (hanya run yang pulih)
  hallucination_rate  run dengan evidence_ids yang tidak ada, ATAU perintah ke
                      router/interface/neighbor yang tidak ada di topologi
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

from rca.catalog import load_catalog
from rca.linter import CommandLinter
from rca.topology import Topology

VARIANT_ORDER = ["zero_shot", "text_rag", "graph_rag", "rule_based"]
TOPO_RULES = {"unknown_router", "unknown_interface", "unknown_neighbor"}


# ------------------------------------------------------------------ baca data


def _get(d: dict, *names, default=None):
    for n in names:
        cur = d
        for part in n.split("."):
            if not isinstance(cur, dict) or part not in cur:
                break
            cur = cur[part]
        else:
            return cur
    return default


def load_runs(path: str | Path) -> list[dict]:
    runs = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{n}: baris JSON tidak valid ({e})")
    return runs


def score_run(run: dict, catalog, linter: CommandLinter) -> dict:
    fault_id = str(_get(run, "fault_id", "fault.id"))
    gt = catalog.get(fault_id)
    agent = _get(run, "agent", "answer", "diagnosis", default={}) or {}
    patch = _get(agent, "proposed_patch", default=[]) or []
    pred_router = _get(agent, "router", "target_router") or (patch[0].get("router") if patch else None)
    pred_class = _get(agent, "root_cause", "root_cause_class", "fault_class", "class")
    commands = _get(agent, "commands", "remediation", default=None) or patch

    lint = _get(run, "lint", "linter", default=None)
    if lint is None:  # runner belum menyimpan hasil linter: hitung ulang
        lint = linter.lint(commands).to_dict()
    lint_passed = bool(lint.get("passed"))

    # halusinasi evidence
    used = list(_get(agent, "evidence_ids", default=[]) or [])
    for item in (_get(agent, "claims", default=[]) or []) + patch:  # kontrak agen: ID ada di claims/patch
        used += [e for e in item.get("evidence_ids", []) if e not in used]
    available = _get(run, "evidence_ids_available", "evidence.ids", "available_evidence_ids")
    bad_ev = [e for e in used if available is not None and e not in set(available)]
    # halusinasi perintah: selalu dicek ulang terhadap topologi
    topo_viol = [v for v in linter.lint(commands).violations if v.rule in TOPO_RULES] if commands else []

    recovered = bool(_get(run, "recovered", "verify.recovered", "verification.passed", default=False))
    applied = bool(_get(run, "applied", "executed", default=lint_passed and bool(commands)))
    return {
        "run_id": _get(run, "run_id", default=f"{fault_id}-{_get(run, 'variant')}-{_get(run, 'trial')}"),
        "fault_id": fault_id,
        "variant": _get(run, "variant"),
        "trial": _get(run, "trial"),
        "gt_router": gt.router if gt else None,
        "gt_class": gt.fault_class if gt else None,
        "pred_router": pred_router,
        "pred_class": pred_class,
        "router_ok": bool(gt and pred_router == gt.router),
        "class_ok": bool(gt and pred_class == gt.fault_class),
        "rca_ok": bool(gt and pred_router == gt.router and pred_class == gt.fault_class),
        "confidence": _get(agent, "confidence"),
        "lint_passed": lint_passed,
        "applied": applied,
        "recovered": recovered,
        "cmd_ok": lint_passed and recovered,
        "halluc_evidence": len(bad_ev) > 0,
        "halluc_command": len(topo_viol) > 0,
        "halluc": len(bad_ev) > 0 or len(topo_viol) > 0,
        "agent_error": bool(_get(run, "error")) or not agent,
        "t_diagnosis_s": _get(run, "t_diagnosis_s", "timing.diagnosis_s", "diagnosis_time_s"),
        "t_recovery_s": _get(run, "t_recovery_s", "timing.recovery_s", "mttr_s") if recovered else None,
        "explanation": _get(agent, "explanation", default="") or " ".join(
            [str(_get(agent, "root_cause_hypothesis", default="") or "")]
            + [c.get("statement", "") for c in (_get(agent, "claims", default=[]) or [])]).strip(),
        "unknown_fault": gt is None,
        "synthetic": bool(run.get("synthetic")),
    }


# ------------------------------------------------------------------ metrik


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def _order(variants) -> list[str]:
    vs = list(dict.fromkeys(variants))
    return sorted(vs, key=lambda v: (VARIANT_ORDER.index(v) if v in VARIANT_ORDER else 99, str(v)))


def metrics_by_variant(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for v in _order(df["variant"]):
        g = df[df["variant"] == v]
        n = len(g)
        k = int(g["rca_ok"].sum())
        lo, hi = wilson(k, n)
        td = pd.to_numeric(g["t_diagnosis_s"], errors="coerce").dropna()
        tr = pd.to_numeric(g["t_recovery_s"], errors="coerce").dropna()
        applied = g[g["applied"]]
        conf = pd.to_numeric(g["confidence"], errors="coerce")
        rows.append({
            "variant": v,
            "runs": n,
            "rca_accuracy": k / n,
            "rca_ci95_low": lo,
            "rca_ci95_high": hi,
            "router_accuracy": g["router_ok"].mean(),
            "class_accuracy": g["class_ok"].mean(),
            "lint_pass_rate": g["lint_passed"].mean(),
            "command_correctness": g["cmd_ok"].mean(),
            "fix_success_rate": applied["recovered"].mean() if len(applied) else math.nan,
            "recovered_rate": g["recovered"].mean(),
            "t_diag_median_s": td.median() if len(td) else math.nan,
            "t_diag_p90_s": td.quantile(0.9) if len(td) else math.nan,
            "t_recovery_median_s": tr.median() if len(tr) else math.nan,
            "t_recovery_p90_s": tr.quantile(0.9) if len(tr) else math.nan,
            "recovery_under_10s": (tr < 10).sum() / n if n else math.nan,
            "hallucination_rate": g["halluc"].mean(),
            "halluc_evidence_rate": g["halluc_evidence"].mean(),
            "halluc_command_rate": g["halluc_command"].mean(),
            "agent_error_rate": g["agent_error"].mean(),
            "conf_when_correct": conf[g["rca_ok"]].mean(),
            "conf_when_wrong": conf[~g["rca_ok"]].mean(),
        })
    return pd.DataFrame(rows)


def accuracy_by_class(df: pd.DataFrame) -> pd.DataFrame:
    t = df.pivot_table(index="gt_class", columns="variant", values="rca_ok", aggfunc="mean")
    return t[[v for v in _order(df["variant"]) if v in t.columns]]


# ------------------------------------------------------------------ keluaran


def _md_table(df: pd.DataFrame, pct_cols: set[str], sec_cols: set[str]) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" if i == 0 else "---:"
                                                          for i in range(len(cols))) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, float) and math.isnan(v):
                cells.append("–")
            elif c in pct_cols:
                cells.append(f"{100 * v:.1f}%")
            elif c in sec_cols:
                cells.append(f"{v:.2f}")
            elif isinstance(v, float):
                cells.append(f"{v:.2f}")
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


HEADLINE = {
    "variant": "Varian", "runs": "Run", "rca_accuracy": "Akurasi akar masalah", "command_correctness":
    "Ketepatan perintah", "fix_success_rate": "Keberhasilan perbaikan", "t_diag_median_s": "Diagnosis median (s)",
    "t_diag_p90_s": "Diagnosis p90 (s)", "t_recovery_median_s": "Pemulihan median (s)",
    "t_recovery_p90_s": "Pemulihan p90 (s)", "hallucination_rate": "Halusinasi",
}


def boxplot(df: pd.DataFrame, col: str, title: str, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = _order(df["variant"])
    data = [pd.to_numeric(df[df["variant"] == v][col], errors="coerce").dropna().values for v in order]
    fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=150)
    bp = ax.boxplot(data, tick_labels=[f"{v}\n(n={len(d)})" for v, d in zip(order, data)], patch_artist=True,
                    widths=0.5, medianprops={"color": "#1f1f1f", "linewidth": 1.6},
                    flierprops={"marker": "o", "markersize": 3, "markerfacecolor": "#888", "markeredgecolor": "none"})
    palette = ["#4C78A8", "#F58518", "#54A24B", "#B279A2"]
    for patch, c in zip(bp["boxes"], palette * 2):
        patch.set_facecolor(c)
        patch.set_alpha(0.75)
        patch.set_edgecolor("#333")
    if col == "t_recovery_s":
        ax.axhline(10, color="#C44E52", linestyle="--", linewidth=1, label="target 10 s")
        ax.legend(frameon=False, loc="upper left")
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("detik")
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def evaluate(results: Path, out: Path, catalog_path: Path | None = None, topology_path: Path | None = None) -> dict:
    catalog = load_catalog(catalog_path)
    linter = CommandLinter(Topology.load(topology_path))
    runs = load_runs(results)
    if not runs:
        raise SystemExit(f"{results}: tidak ada run")
    df = pd.DataFrame([score_run(r, catalog, linter) for r in runs])
    out.mkdir(parents=True, exist_ok=True)

    m = metrics_by_variant(df)
    c = accuracy_by_class(df)
    df.drop(columns=["explanation"]).to_csv(out / "runs_scored.csv", index=False)
    m.to_csv(out / "metrics_by_variant.csv", index=False)
    c.to_csv(out / "accuracy_by_class.csv")

    pct = {"rca_accuracy", "command_correctness", "fix_success_rate", "hallucination_rate"}
    head = m[list(HEADLINE)].rename(columns=HEADLINE)
    lines = [f"# Hasil evaluasi: {results.name}", ""]
    if df["synthetic"].any():
        lines += ["> **PERINGATAN: data sintetis** — hanya untuk menguji evaluator, bukan hasil eksperimen.", ""]
    if df["unknown_fault"].any():
        lines += [f"> {int(df['unknown_fault'].sum())} run memakai fault_id yang tidak ada di katalog.", ""]
    lines += ["## Ringkasan per varian", "",
              _md_table(head, {HEADLINE[p] for p in pct}, set()), "",
              "Akurasi = router dan kelas akar masalah cocok dengan ground truth. Ketepatan perintah = lolos linter "
              "dan jaringan pulih. Keberhasilan perbaikan = pulih di antara run yang perintahnya dijalankan. "
              "Waktu pemulihan dihitung sejak gejala terdeteksi, hanya untuk run yang pulih.", "",
              "## Akurasi per kelas fault", "", _md_table(c.reset_index(), set(c.columns), set()), "",
              "## Detail", "",
              _md_table(m[["variant", "rca_ci95_low", "rca_ci95_high", "router_accuracy", "class_accuracy",
                           "lint_pass_rate", "recovery_under_10s", "halluc_evidence_rate", "halluc_command_rate",
                           "agent_error_rate", "conf_when_correct", "conf_when_wrong"]],
                        {"rca_ci95_low", "rca_ci95_high", "router_accuracy", "class_accuracy", "lint_pass_rate",
                         "recovery_under_10s", "halluc_evidence_rate", "halluc_command_rate", "agent_error_rate"},
                        set()), "",
              "![Waktu diagnosis](boxplot_diagnosis_time.png)", "", "![Waktu pemulihan](boxplot_recovery_time.png)"]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    boxplot(df, "t_diagnosis_s", "Waktu diagnosis per varian", out / "boxplot_diagnosis_time.png")
    boxplot(df, "t_recovery_s", "Waktu sampai jaringan pulih per varian", out / "boxplot_recovery_time.png")
    return {"runs": len(df), "metrics": m, "by_class": c, "scored": df}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hitung metrik per varian dari file hasil run.")
    ap.add_argument("results", type=Path, help="file JSON Lines hasil runner")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--catalog", type=Path, default=None)
    ap.add_argument("--topology", type=Path, default=None)
    args = ap.parse_args(argv)
    out = args.out or Path("results") / "eval" / args.results.stem
    res = evaluate(args.results, out, args.catalog, args.topology)
    pd.set_option("display.width", 160)
    print(res["metrics"][["variant", "runs", "rca_accuracy", "command_correctness", "fix_success_rate",
                          "t_diag_median_s", "t_diag_p90_s", "t_recovery_median_s", "hallucination_rate"]]
          .to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print(f"\nLaporan: {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
