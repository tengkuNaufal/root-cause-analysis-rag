#!/usr/bin/env python3
# Menampilkan progres sesi bench.py dan detail satu run, buat monitoring dan demo. Cuma baca file
# hasil, gak nyentuh lab atau API, jadi aman dijalankan pas benchmark lagi jalan.
#
#   python3 scripts/bench_status.py data/host2/bench
#   python3 scripts/bench_status.py data/host2/bench --show 12      # detail baris jadwal 12
#   python3 scripts/bench_status.py data/host2/demo --show last
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fault_runner as fr  # noqa: E402


def read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass  # baris terakhir bisa setengah ketulis kalau dibaca pas runner lagi nulis
    return rows


def fmt(v):
    return "-" if v is None else f"{v:.1f}s"


def assessment(rec):
    return ((rec.get("diagnosis") or {}).get("assessment")) or {}


def latest(results):
    # Mengambil attempt terakhir per baris jadwal biar retry gak dihitung dobel.
    out = {}
    for r in results:
        if r["plan_order"] not in out or r["attempt"] >= out[r["plan_order"]]["attempt"]:
            out[r["plan_order"]] = r
    return [out[k] for k in sorted(out)]


def summary(out, faults, plan_total):
    rows = latest(read_jsonl(out / "results.jsonl"))
    journal = read_jsonl(out / "journal.jsonl")
    print(f"Sesi {out}: {len(rows)} baris selesai" + (f" dari {plan_total} jadwal penuh" if plan_total else ""))
    # A held attempt may exist before the first final row, or after retrying an older final row.
    done = {(r['plan_order'], r.get('attempt', 1)) for r in read_jsonl(out / 'results.jsonl')}
    pending = {}
    for event in journal:
        order = event.get('plan_order', event.get('order'))
        key = (order, event.get('attempt', 1))
        if event.get('event') == 'held' and key not in done:
            pending[key] = event
    for (order, attempt), event in pending.items():
        print(f"\nPERINGATAN: baris {order} attempt {attempt} ditahan (fault mungkin masih terpasang); "
              "resume sesi yang sama untuk rekonsiliasi, jangan mulai sesi baru")
    if not rows:
        return
    print(f"\n{'varian':<10}{'run':>5}{'kelas':>7}{'router':>8}{'lint ok':>9}{'agen':>6}{'pulih':>7}"
          f"{'diag med':>10}{'pulih med':>11}")
    for variant in sorted({r["variant"] for r in rows}):
        part = [r for r in rows if r["variant"] == variant]
        cls = sum(assessment(r).get("root_cause") == faults.get(r["fault_id"], {}).get("class") for r in part)
        rtr = sum(assessment(r).get("router") == faults.get(r["fault_id"], {}).get("ground_truth", {}).get("router")
                  for r in part)
        lint = sum((r.get("lint") or {}).get("status") == "passed" for r in part)
        agent = sum(bool((r.get("execution") or {}).get("agent_recovered")) for r in part)
        rec = sum(r.get("recovered") is True for r in part)
        diag = [r["timing"]["diagnosis_s"] for r in part if (r.get("timing") or {}).get("diagnosis_s") is not None]
        heal = [r["timing"]["agent_recovery_s"] for r in part
                if (r.get("timing") or {}).get("agent_recovery_s") is not None]
        print(f"{variant:<10}{len(part):>5}{cls:>7}{rtr:>8}{lint:>9}{agent:>6}{rec:>7}"
              f"{fmt(statistics.median(diag) if diag else None):>10}"
              f"{fmt(statistics.median(heal) if heal else None):>11}")
    print("(kelas/router = cocok dengan katalog, cuma cek cepat; angka resmi tetap dari evaluator)")

    bad = [r for r in rows if r["status"] != "completed" or r.get("recovered") is not True]
    if bad:
        print("\nBaris yang perlu dicek:")
        for r in bad[-10:]:
            print(f"  [{r['plan_order']}] {r['fault_id']} {r['variant']} status={r['status']} "
                  f"pulih={r.get('recovered')} {(r.get('error') or '')[:80]}")

    print("\nRun terakhir:")
    for r in rows[-5:]:
        a = assessment(r)
        print(f"  [{r['plan_order']}] {r['fault_id']} {r['variant']:<9} {r['status']:<12} "
              f"diagnosis={a.get('root_cause', '-')}@{a.get('router', '-')} "
              f"lint={(r.get('lint') or {}).get('status', '-')} applied={r.get('applied')} "
              f"agen_pulihkan={fmt((r.get('timing') or {}).get('agent_recovery_s'))} pulih={r.get('recovered')}")


def show(out, faults, which):
    rows = latest(read_jsonl(out / "results.jsonl"))
    if not rows:
        sys.exit(f"Belum ada hasil di {out}")
    rec = rows[-1] if which == "last" else next((r for r in rows if str(r["plan_order"]) == which), None)
    if rec is None:
        sys.exit(f"Baris {which} gak ada di {out}")
    fault = faults.get(rec["fault_id"], {})
    a, t = assessment(rec), rec.get("timing") or {}
    lint = rec.get("lint") or {}
    print(f"Baris {rec['plan_order']} attempt {rec['attempt']}: {rec['fault_id']} varian {rec['variant']} "
          f"trial {rec['trial']}, status {rec['status']}")
    truth = fault.get("ground_truth", {})
    print(f"\nFault yang disuntik : {fault.get('class')} di {fault.get('link') or truth.get('router')} "
          f"({truth.get('root_cause', '-')})")
    print("Gejala terdeteksi   :")
    for s in (rec.get("symptoms") or [])[:6]:
        print(f"  - {s}")
    print(f"\nDiagnosis agen      : {a.get('root_cause', '-')} di {a.get('router', '-')}, "
          f"confidence {a.get('confidence', '-')}")
    if a.get("explanation"):
        print(f"Penjelasan          : {a['explanation']}")
    print(f"Evidence dipakai    : {', '.join(a.get('evidence_ids') or []) or '-'}")
    print("Perintah perbaikan  :")
    for c in a.get("commands") or []:
        args = c.get("args") or []
        line = "ip " + " ".join(args) if c.get("interpreter") == "ip" else "vtysh " + " ".join(f'-c "{a}"' for a in args)
        print(f"  {c.get('router')}: {line}")
    print(f"Linter              : {lint.get('status', '-')}" +
          (f" ({'; '.join(map(str, lint.get('violations') or []))})" if lint.get("violations") else ""))
    print(f"Diterapkan          : {rec.get('applied')}")
    ex = rec.get("execution") or {}
    if ex:
        print(f"Agen memulihkan lab : {ex.get('agent_recovered')}")
    fb = rec.get("fallback_revert") or {}
    if fb.get("performed"):
        print(f"Fallback revert     : ya ({fb.get('reason')})")
    print(f"Lab pulih           : {rec.get('recovered')}")
    print(f"\nWaktu: deteksi {fmt(t.get('detection_s'))}, diagnosis {fmt(t.get('diagnosis_s'))}, "
          f"pemulihan oleh agen {fmt(t.get('agent_recovery_s'))}, fallback {fmt(t.get('fallback_recovery_s'))}")
    if rec.get("error"):
        print(f"Error: {rec['error']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", help="folder sesi bench.py, misalnya data/host2/bench")
    ap.add_argument("--show", help="nomor baris jadwal atau 'last' untuk detail satu run")
    ap.add_argument("--catalog", default=str(fr.ROOT / "faults" / "host1.yaml"))
    ap.add_argument("--plan", default=str(fr.ROOT / "data" / "benchmark_plan.csv"))
    args = ap.parse_args()
    out = Path(args.out)
    faults = {f["id"]: f for f in fr.load_catalog(args.catalog)}
    if args.show:
        show(out, faults, args.show)
        return
    plan = Path(args.plan)
    total = max(len(plan.read_text().splitlines()) - 1, 0) if plan.exists() else None
    summary(out, faults, total)


if __name__ == "__main__":
    main()
