"""Evaluator: membaca file hasil run (JSON Lines) dan katalog, lalu menghitung metrik per varian.

    python -m rca.evaluator data/host2/<hasil>.jsonl --out results/eval/pilot

Bentuk baris utama mengikuti "Catatan JSONL milik Host 2" di docs/host1/LIVE-API-DRAFT.md:
{
  "plan_order": 1, "fault_id": "F01", "variant": "graph_rag", "trial": 1, "request_id": "...", "job_id": "...",
  "timing": {"t_inject": ..., "t_symptom": ..., "t_request": ..., "t_diagnosis_done": ...,
             "t_lint_done": ..., "t_apply_done": null, "t_verified": ...},
  "diagnosis": {...respons API utuh: state, result, assessment{router, root_cause, confidence,
                evidence_ids, commands, explanation}, evidence[manifest], timing, provenance...},
  "lint": {"status": "passed|rejected|error|not_requested", "violations": [...], ...},
  "execution": null,                      # null / applied=false selama tahap read-only
  "verification": {...}, "fallback_revert": {"performed": true, "reason": "..."},
  "recovered": true, "error": null, "status": "..."
}
Titik waktu `timing.t_*` boleh berupa angka elapsed monotonic (detik), objek {"utc", "elapsed_s"},
field `t_*_elapsed_s` / `t_*_utc`, atau string UTC. Bentuk lama (`agent{...}`, `t_diagnosis_s`,
`t_recovery_s`, `lint.passed`) tetap diterima.

Metrik per varian:
  rca_accuracy        router DAN kelas akar masalah (assessment) cocok dengan ground truth katalog
  command_correctness perintah lolos linter DAN jaringan pulih OLEH PERINTAH AGEN (dibagi semua run)
  fix_success_rate    pulih oleh perintah agen di antara run yang perintahnya benar-benar dijalankan;
                      kosong (–) selama read-only. `applied` default false; pemulihan lewat fallback
                      revert katalog tidak pernah dihitung sebagai keberhasilan agen.
  t_diagnosis         t_diagnosis_done - t_symptom (median, p90)
  t_recovery          t_verified - t_symptom, hanya run yang dipulihkan agen (median, p90)
  hallucination_rate  run dengan evidence_ids di luar manifest evidence, ATAU perintah ke
                      router/interface/neighbor yang tidak ada di topologi
  abstain_rate, incomplete_rate (router null / kelas unknown), agent_error_rate dicatat terpisah.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
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


def _agent_view(run: dict) -> dict:
    """Ambil jawaban agen dari berbagai bentuk baris JSONL.

    Bentuk live API (docs/host1/LIVE-API-DRAFT.md): `diagnosis` = respons API utuh, jawaban terstruktur di
    `diagnosis.assessment`, manifest evidence di `diagnosis.evidence`, respons internal di `diagnosis.result`.
    Bentuk lama: `agent` / `answer` berisi router, root_cause, commands, ... langsung.
    """
    diag = run.get("diagnosis")
    if isinstance(diag, dict) and ({"assessment", "state", "result", "job_id"} & set(diag)):
        a = diag.get("assessment") or {}
        res = diag.get("result") or {}
        manifest = diag.get("evidence")
        claims = res.get("claims") or []
        return {
            "router": a.get("router"),
            "root_cause": a.get("root_cause"),
            "confidence": a.get("confidence", res.get("confidence")),
            "evidence_ids": list(a.get("evidence_ids") or []),
            "commands": a.get("commands") or res.get("proposed_patch") or [],
            "explanation": a.get("explanation") or " ".join(
                [str(res.get("root_cause_hypothesis") or "")] + [c.get("statement", "") for c in claims]).strip(),
            "available": [e.get("id") for e in manifest if isinstance(e, dict)] if isinstance(manifest, list) else None,
            "state": diag.get("state"),
            "status": res.get("status"),
            "variant": diag.get("variant"),
            "simulation": bool(diag.get("simulation")),
            "present": bool(a or res),
        }
    agent = _get(run, "agent", "answer", "diagnosis", default={}) or {}
    patch = _get(agent, "proposed_patch", default=[]) or []
    used = list(_get(agent, "evidence_ids", default=[]) or [])
    for item in (_get(agent, "claims", default=[]) or []) + patch:  # kontrak agen: ID ada di claims/patch
        used += [e for e in item.get("evidence_ids", []) if e not in used]
    return {
        "router": _get(agent, "router", "target_router") or (patch[0].get("router") if patch else None),
        "root_cause": _get(agent, "root_cause", "root_cause_class", "fault_class", "class"),
        "confidence": _get(agent, "confidence"),
        "evidence_ids": used,
        "commands": _get(agent, "commands", "remediation", default=None) or patch,
        "explanation": _get(agent, "explanation", default="") or " ".join(
            [str(_get(agent, "root_cause_hypothesis", default="") or "")]
            + [c.get("statement", "") for c in (_get(agent, "claims", default=[]) or [])]).strip(),
        "available": _get(run, "evidence_ids_available", "evidence.ids", "available_evidence_ids"),
        "state": None,
        "status": _get(agent, "status"),
        "variant": None,
        "simulation": False,
        "present": bool(agent),
    }


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _elapsed(v) -> float | None:
    if isinstance(v, dict):
        for k in ("elapsed_s", "elapsed_seconds", "elapsed", "monotonic_s", "monotonic"):
            if _num(v.get(k)) is not None:
                return _num(v[k])
        return None
    return _num(v)


def _utc(v) -> datetime | None:
    if isinstance(v, dict):
        v = v.get("utc")
    if not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration(run: dict, start: str, end: str) -> float | None:
    """Selisih dua titik waktu runner (timing.t_symptom, t_diagnosis_done, t_verified, ...).

    Nilai titik waktu boleh angka (elapsed monotonic, detik), objek {utc, elapsed_s}, field terpisah
    `<nama>_elapsed_s` / `<nama>_utc`, atau string UTC. Elapsed monotonic diutamakan; UTC hanya cadangan.
    """
    t = run.get("timing") or {}

    def pick(name, conv, suffixes):
        for s in suffixes:
            x = conv(t.get(name + s))
            if x is not None:
                return x
        return None

    a = pick(start, _elapsed, ("", "_elapsed_s", "_s"))
    b = pick(end, _elapsed, ("", "_elapsed_s", "_s"))
    if a is not None and b is not None:
        return round(b - a, 3)
    ua, ub = pick(start, _utc, ("", "_utc")), pick(end, _utc, ("", "_utc"))
    if ua and ub:
        return round((ub - ua).total_seconds(), 3)
    return None


def score_run(run: dict, catalog, linter: CommandLinter) -> dict:
    fault_id = str(_get(run, "fault_id", "fault.id"))
    gt = catalog.get(fault_id)
    ag = _agent_view(run)
    pred_router, pred_class, commands = ag["router"], ag["root_cause"], ag["commands"]

    lint = _get(run, "lint", "linter", default=None)
    if lint is None:  # runner belum menyimpan hasil linter: hitung ulang
        lint = linter.lint(commands).to_dict()
    # bentuk lama {"passed": bool}; bentuk live {"status": passed|rejected|error|not_requested}
    lint_passed = lint.get("passed") is True or lint.get("status") == "passed"

    # halusinasi evidence: ID yang dipakai agen tetapi tidak ada di manifest/daftar yang dikirim
    available = ag["available"]
    bad_ev = [e for e in ag["evidence_ids"] if available is not None and e not in set(available)]
    # halusinasi perintah: selalu dicek ulang terhadap topologi
    topo_viol = [v for v in linter.lint(commands).violations if v.rule in TOPO_RULES] if commands else []

    # Eksekusi: default TIDAK dijalankan. Selama tahap read-only runner menulis applied=false /
    # execution=null, dan pemulihan lewat revert katalog tidak dihitung sebagai keberhasilan agen.
    execution = run.get("execution")
    if "applied" in run:
        applied = run["applied"] is True
    elif isinstance(execution, dict):
        applied = execution.get("applied") is True or execution.get("status") in ("applied", "succeeded", "success")
    else:
        applied = False
    recovered = _get(run, "recovered", "verification.recovered", "verify.recovered", "verification.passed",
                     default=False) is True
    reverted = (_get(run, "fallback_revert.performed", default=False) is True or run.get("reverted") is True
                or _get(run, "verification.source", default=None) in ("fallback_revert", "catalog_revert"))
    agent_recovered = applied and recovered and not reverted

    t_diag = _num(_get(run, "t_diagnosis_s", "timing.diagnosis_s", "diagnosis_time_s"))
    if t_diag is None:
        t_diag = _duration(run, "t_symptom", "t_diagnosis_done")
    t_rec = _num(_get(run, "t_recovery_s", "timing.recovery_s", "mttr_s"))
    if t_rec is None:
        t_rec = _duration(run, "t_symptom", "t_verified")

    diag_failed = (bool(run.get("error")) or ag["state"] in ("failed", "interrupted") or not ag["present"]
                   or run.get("status") in ("timeout", "error"))
    sched_variant = _get(run, "variant")
    return {
        "run_id": _get(run, "run_id", "request_id", default=f"{fault_id}-{sched_variant}-{_get(run, 'trial')}"),
        "fault_id": fault_id,
        "variant": sched_variant or ag["variant"],
        "trial": _get(run, "trial"),
        "gt_router": gt.router if gt else None,
        "gt_class": gt.fault_class if gt else None,
        "pred_router": pred_router,
        "pred_class": pred_class,
        "router_ok": bool(gt and pred_router == gt.router),
        "class_ok": bool(gt and pred_class == gt.fault_class),
        "rca_ok": bool(gt and pred_router == gt.router and pred_class == gt.fault_class),
        "confidence": ag["confidence"],
        "has_commands": bool(commands),
        "lint_passed": lint_passed,
        "applied": applied,
        "recovered": recovered,
        "fallback_revert": reverted,
        "agent_recovered": agent_recovered,
        "cmd_ok": lint_passed and agent_recovered,
        "halluc_evidence": len(bad_ev) > 0,
        "halluc_command": len(topo_viol) > 0,
        "halluc": len(bad_ev) > 0 or len(topo_viol) > 0,
        "agent_error": diag_failed,
        "abstain": ag["status"] == "abstain",
        "incomplete_prediction": pred_router is None or pred_class in (None, "", "unknown"),
        "variant_mismatch": bool(ag["variant"] and sched_variant and ag["variant"] != sched_variant),
        "t_diagnosis_s": t_diag,
        "t_recovery_s": t_rec if agent_recovered else None,
        "explanation": ag["explanation"] or "",
        "unknown_fault": gt is None,
        "synthetic": bool(run.get("synthetic")) or ag["simulation"],
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
            "fix_success_rate": applied["agent_recovered"].mean() if len(applied) else math.nan,
            "applied_rate": g["applied"].mean(),
            "recovered_any_rate": g["recovered"].mean(),
            "fallback_revert_rate": g["fallback_revert"].mean(),
            "t_diag_median_s": td.median() if len(td) else math.nan,
            "t_diag_p90_s": td.quantile(0.9) if len(td) else math.nan,
            "t_recovery_median_s": tr.median() if len(tr) else math.nan,
            "t_recovery_p90_s": tr.quantile(0.9) if len(tr) else math.nan,
            "recovery_under_10s": (tr < 10).sum() / n if n else math.nan,
            "hallucination_rate": g["halluc"].mean(),
            "halluc_evidence_rate": g["halluc_evidence"].mean(),
            "halluc_command_rate": g["halluc_command"].mean(),
            "agent_error_rate": g["agent_error"].mean(),
            "abstain_rate": g["abstain"].mean(),
            "incomplete_rate": g["incomplete_prediction"].mean(),
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
              "dan jaringan pulih oleh perintah agen. Keberhasilan perbaikan = pulih oleh perintah agen di antara run "
              "yang perintahnya dijalankan (– bila belum ada eksekusi). Pemulihan lewat fallback revert katalog tidak "
              "dihitung. Waktu diagnosis = t_diagnosis_done − t_symptom; waktu pemulihan = t_verified − t_symptom, "
              "hanya untuk run yang dipulihkan agen.", "",
              "## Akurasi per kelas fault", "", _md_table(c.reset_index(), set(c.columns), set()), "",
              "## Detail", "",
              _md_table(m[["variant", "rca_ci95_low", "rca_ci95_high", "router_accuracy", "class_accuracy",
                           "lint_pass_rate", "recovery_under_10s", "halluc_evidence_rate", "halluc_command_rate",
                           "agent_error_rate", "abstain_rate", "incomplete_rate", "applied_rate",
                           "fallback_revert_rate", "conf_when_correct", "conf_when_wrong"]],
                        {"rca_ci95_low", "rca_ci95_high", "router_accuracy", "class_accuracy", "lint_pass_rate",
                         "recovery_under_10s", "halluc_evidence_rate", "halluc_command_rate", "agent_error_rate",
                         "abstain_rate", "incomplete_rate", "applied_rate", "fallback_revert_rate"},
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
