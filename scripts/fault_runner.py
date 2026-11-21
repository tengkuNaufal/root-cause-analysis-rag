#!/usr/bin/env python3
# Menjalankan fault dari faults/catalog.yaml satu per satu: cek awal, inject, tunggu gejala,
# simpan evidence, revert, lalu nunggu lab balik normal. Hasilnya satu baris JSON per fault.
#
#   python3 scripts/fault_runner.py list
#   python3 scripts/fault_runner.py run F01 F16
#   python3 scripts/fault_runner.py run --all
#   python3 scripts/fault_runner.py plan --seed 42
import argparse
import csv
import json
import random
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_lab import EXPECTED, check  # noqa: E402

LAB = "topik8"
ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "faults" / "catalog.yaml"
VARIANTS = ["zero_shot", "text_rag", "graph_rag"]


def load_catalog():
    return yaml.safe_load(CATALOG.read_text())["faults"]


def container(router):
    return f"clab-{LAB}-{router}"


def apply_steps(router, steps):
    for step in steps:
        if step["type"] == "shell":
            cmd = ["docker", "exec", container(router), *shlex.split(step["cmd"])]
        elif step["type"] == "vtysh":
            cmd = ["docker", "exec", container(router), "vtysh"]
            for line in step["lines"]:
                cmd += ["-c", line]
        else:
            raise ValueError(f"tipe langkah tidak dikenal: {step['type']}")
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if p.returncode != 0 or "%" in p.stdout:
            raise RuntimeError(f"{router}: {' '.join(cmd[3:])} gagal: {p.stdout.strip()} {p.stderr.strip()}")


# Mengambil rute terpilih ke loopback router lain, buat dibandingin sama kondisi awal.
# Fault BGP yang ada jalur cadangannya cuma kelihatan dari sini, ping-nya tetap lolos.
def loopback_routes():
    table = {}
    for r in EXPECTED[LAB]:
        out = subprocess.run(["docker", "exec", container(r), "vtysh", "-c", "show ip route json"],
                             capture_output=True, text=True, timeout=20).stdout
        rows = {}
        for prefix, entries in json.loads(out or "{}").items():
            if not prefix.startswith("10.255.0.") or prefix == f"10.255.0.{r[1:]}/32":
                continue
            best = next((e for e in entries if e.get("selected")), None)
            if best:
                hops = sorted(h.get("ip", h.get("interfaceName", "?")) for h in best.get("nexthops", []))
                rows[prefix] = [best["protocol"], hops]
        table[r] = rows
    return table


def route_diff(base, now):
    diffs = []
    for r in base:
        for prefix in sorted(set(base[r]) | set(now.get(r, {}))):
            a, b = base[r].get(prefix), now.get(r, {}).get(prefix)
            if a != b:
                diffs.append(f"{r} {prefix}: {fmt_route(a)} -> {fmt_route(b)}")
    return diffs


def fmt_route(x):
    return "tidak ada" if x is None else f"{x[0]} via {','.join(x[1])}"


def symptoms(base_routes):
    snap = check(LAB)
    return snap, snap["failures"] + route_diff(base_routes, loopback_routes())


def wait_for(fn, timeout, interval=1.0):
    start = time.monotonic()
    while True:
        value = fn()
        elapsed = time.monotonic() - start
        if value or elapsed > timeout:
            return value, elapsed
        time.sleep(interval)


def run_fault(fault, base_routes, symptom_timeout, recover_timeout):
    rec = {"fault_id": fault["id"], "class": fault["class"], "ground_truth": fault["ground_truth"],
           "started_at_utc": datetime.now(timezone.utc).isoformat()}
    t0 = time.monotonic()
    apply_steps(fault["inject"]["router"], fault["inject"]["steps"])
    rec["t_inject_s"] = round(time.monotonic() - t0, 2)

    seen, t_sym = wait_for(lambda: symptoms(base_routes)[1], symptom_timeout, interval=2)
    rec["observable"] = bool(seen)
    rec["t_symptom_s"] = round(t_sym, 1) if seen else None
    rec["symptoms"] = seen or []
    if seen:
        evidence, _ = symptoms(base_routes)
        rec["evidence"] = {"failures": evidence["failures"], "ping_ok": sum(evidence["ping"].values()),
                           "ping_total": len(evidence["ping"])}

    t1 = time.monotonic()
    apply_steps(fault["revert"]["router"], fault["revert"]["steps"])
    healthy, t_rec = wait_for(lambda: not symptoms(base_routes)[1], recover_timeout, interval=2)
    rec["recovered"] = bool(healthy)
    rec["t_recover_s"] = round(time.monotonic() - t1, 1) if healthy else None
    rec["t_total_s"] = round(time.monotonic() - t0, 1)
    return rec


def cmd_run(args):
    faults = load_catalog()
    if not args.all:
        wanted = set(args.ids)
        faults = [f for f in faults if f["id"] in wanted]
        missing = wanted - {f["id"] for f in faults}
        if missing:
            sys.exit(f"ID tidak ada di katalog: {', '.join(sorted(missing))}")

    base = check(LAB)
    if base["failures"]:
        sys.exit("Baseline tidak sehat, jalankan check_lab.py dulu:\n  " + "\n  ".join(base["failures"]))
    base_routes = loopback_routes()

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"faults_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    with path.open("w") as fh:
        for f in faults:
            rec = run_fault(f, base_routes, args.symptom_timeout, args.recover_timeout)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            status = "OK" if rec["observable"] and rec["recovered"] else "PERIKSA"
            print(f"{f['id']} {f['class']:<22} gejala {fmt_t(rec['t_symptom_s'])} "
                  f"({len(rec['symptoms'])} temuan)  pulih {fmt_t(rec['t_recover_s'])}  {status}", flush=True)
            if not rec["recovered"]:
                print("Lab tidak pulih, run dihentikan supaya fault berikutnya tidak kecampur.")
                break
    print(f"Hasil: {path}")


def fmt_t(v):
    return "  -   " if v is None else f"{v:5.1f}s"


def cmd_list(_args):
    for f in load_catalog():
        print(f"{f['id']}  {f['class']:<22} {f['link']:<6} {f['ground_truth']['root_cause']}")


def cmd_plan(args):
    rows = [(f["id"], v, t) for f in load_catalog() for v in VARIANTS for t in range(1, args.trials + 1)]
    random.Random(args.seed).shuffle(rows)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["order", "fault_id", "variant", "trial"])
        for i, (fid, v, t) in enumerate(rows, 1):
            w.writerow([i, fid, v, t])
    print(f"{len(rows)} run dijadwalkan (seed {args.seed}) -> {out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("ids", nargs="*")
    r.add_argument("--all", action="store_true")
    r.add_argument("--symptom-timeout", type=float, default=70)
    r.add_argument("--recover-timeout", type=float, default=120)
    r.add_argument("--out", default="data/runs")
    p = sub.add_parser("plan")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--trials", type=int, default=5)
    p.add_argument("--out", default="data/benchmark_plan.csv")
    args = ap.parse_args()
    {"list": cmd_list, "run": cmd_run, "plan": cmd_plan}[args.cmd](args)


if __name__ == "__main__":
    main()
