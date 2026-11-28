#!/usr/bin/env python3
# Menjalankan fault dari katalog satu per satu: cek awal, inject, tunggu gejala,
# simpan evidence, revert, lalu nunggu lab balik normal. Hasilnya satu baris JSON per fault.
# Katalog default-nya faults/host1.yaml (lab rca), nama lab diambil dari field `lab` di katalog.
#
#   python3 scripts/fault_runner.py list
#   python3 scripts/fault_runner.py run F01 F16
#   python3 scripts/fault_runner.py run --all
#   python3 scripts/fault_runner.py --catalog faults/replica.yaml run --all
#   python3 scripts/fault_runner.py plan --seed 42
#   python3 scripts/fault_runner.py revert F07          # manual, kalau run berhenti dengan fault masih kepasang
#
# Exit code run: 0 semua ok, 1 ada fault tanpa gejala, 2 error, 3 lab gak pulih.
import argparse
import csv
import hashlib
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

ROOT = Path(__file__).resolve().parent.parent
LAB = None
VARIANTS = ["zero_shot", "text_rag", "graph_rag"]


def load_catalog(path):
    global LAB
    doc = yaml.safe_load(Path(path).read_text())
    LAB = doc["lab"]
    return doc["faults"]


def container(router):
    return f"clab-{LAB}-{router}"


def apply_steps(router, steps):
    for step in steps:
        if step["type"] == "shell":
            run_argv(router, shlex.split(step["cmd"]))
        elif step["type"] == "vtysh":
            run_argv(router, vtysh_argv(step["lines"]))
        else:
            raise ValueError(f"tipe langkah tidak dikenal: {step['type']}")


def vtysh_argv(lines):
    argv = ["vtysh"]
    for line in lines:
        argv += ["-c", line]
    return argv


def run_argv(router, argv):
    cmd = ["docker", "exec", container(router), *argv]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    # Mengabaikan catatan mgmtd "applied with notes" soalnya perintahnya tetap kepasang.
    errors = [l for l in p.stdout.splitlines()
              if l.startswith("%") and not l.startswith("% Configuration applied with notes")]
    if p.returncode != 0 or errors:
        raise RuntimeError(f"{router}: {' '.join(argv)} gagal: {p.stdout.strip()} {p.stderr.strip()}")
    return p.stdout


# Mengambil hash running-config tiap router, buat ngecek konfigurasi FRR masih sama dengan baseline.
def config_digests():
    out = {}
    for r in EXPECTED[LAB]:
        text = run_argv(r, ["vtysh", "-c", "show running-config"])
        body = text[text.find("frr version"):] if "frr version" in text else text
        out[r] = hashlib.sha256(body.encode()).hexdigest()
    return out


# Mengembalikan satu router ke baseline: semua interface data MTU 1500 dan up, lalu konfigurasi FRR
# disamakan lagi dengan startup-config lewat frr-reload.
def reset_router(router):
    for ifc in EXPECTED[LAB][router]["ifaces"]:
        run_argv(router, ["ip", "link", "set", ifc, "mtu", "1500", "up"])
    run_argv(router, ["python3", "/usr/lib/frr/frr-reload.py", "--reload", "/etc/frr/frr.conf"])


# Mengambil rute terpilih ke alamat ping router lain, buat dibandingin sama kondisi awal.
# Fault BGP yang ada jalur cadangannya cuma kelihatan dari sini, ping-nya tetap lolos.
def loopback_routes():
    targets = {f"{e['addr']}/32": r for r, e in EXPECTED[LAB].items()}
    table = {}
    for r in EXPECTED[LAB]:
        out = subprocess.run(["docker", "exec", container(r), "vtysh", "-c", "show ip route json"],
                             capture_output=True, text=True, timeout=20).stdout
        rows = {}
        for prefix, entries in json.loads(out or "{}").items():
            if targets.get(prefix, r) == r:
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
           "started_at_utc": datetime.now(timezone.utc).isoformat(), "observable": False,
           "t_symptom_s": None, "symptoms": [], "recovered": False, "t_recover_s": None, "error": None}
    t0 = time.monotonic()
    try:
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
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    finally:
        # Selalu revert, termasuk kalau inject atau observasi gagal di tengah.
        rec.update(revert_and_verify(fault, base_routes, recover_timeout))
    rec["t_total_s"] = round(time.monotonic() - t0, 1)
    rec["status"] = classify(rec)
    return rec


def revert_and_verify(fault, base_routes, recover_timeout):
    out = {"revert_error": None}
    t1 = time.monotonic()
    try:
        apply_steps(fault["revert"]["router"], fault["revert"]["steps"])
    except Exception as e:
        out["revert_error"] = f"{type(e).__name__}: {e}"
    try:
        healthy, _ = wait_for(lambda: not symptoms(base_routes)[1], recover_timeout, interval=2)
    except Exception as e:
        healthy = False
        out["revert_error"] = out["revert_error"] or f"{type(e).__name__}: {e}"
    out["recovered"] = bool(healthy)
    out["t_recover_s"] = round(time.monotonic() - t1, 1) if healthy else None
    return out


def classify(rec):
    if not rec["recovered"]:
        return "not_recovered"
    if rec["error"]:
        return "error"
    return "ok" if rec["observable"] else "not_observable"


EXIT = {"ok": 0, "not_observable": 1, "error": 2, "not_recovered": 3}


def check_baseline():
    base = check(LAB)
    if base["failures"]:
        sys.exit("Baseline tidak sehat, jalankan check_lab.py dulu:\n  " + "\n  ".join(base["failures"]))
    return loopback_routes()


def cmd_run(args):
    faults = load_catalog(args.catalog)
    if not args.all:
        wanted = set(args.ids)
        faults = [f for f in faults if f["id"] in wanted]
        missing = wanted - {f["id"] for f in faults}
        if missing:
            sys.exit(f"ID tidak ada di katalog: {', '.join(sorted(missing))}")

    base_routes = check_baseline()
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{LAB}_faults_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    worst = 0
    with path.open("w") as fh:
        for f in faults:
            rec = run_fault(f, base_routes, args.symptom_timeout, args.recover_timeout)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            worst = max(worst, EXIT[rec["status"]])
            print(f"{f['id']} {f['class']:<22} gejala {fmt_t(rec['t_symptom_s'])} "
                  f"({len(rec['symptoms'])} temuan)  pulih {fmt_t(rec['t_recover_s'])}  {rec['status']}", flush=True)
            for key in ("error", "revert_error"):
                if rec.get(key):
                    print(f"    {key}: {rec[key]}")
            if rec["status"] in ("error", "not_recovered"):
                print("Run dihentikan supaya fault berikutnya tidak kecampur. Cek lab dulu sebelum lanjut.")
                break
    print(f"Hasil: {path}")
    sys.exit(worst)


def cmd_revert(args):
    faults = {f["id"]: f for f in load_catalog(args.catalog)}
    if args.id not in faults:
        sys.exit(f"ID tidak ada di katalog: {args.id}")
    f = faults[args.id]
    apply_steps(f["revert"]["router"], f["revert"]["steps"])
    print(f"Revert {args.id} sudah dijalankan. Cek lab dengan check_lab.py sebelum lanjut.")


def fmt_t(v):
    return "  -   " if v is None else f"{v:5.1f}s"


def cmd_list(args):
    for f in load_catalog(args.catalog):
        print(f"{f['id']}  {f['class']:<22} {f['link']:<10} {f['ground_truth']['root_cause']}")


def cmd_plan(args):
    rows = [(f["id"], v, t) for f in load_catalog(args.catalog) for v in VARIANTS for t in range(1, args.trials + 1)]
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
    ap.add_argument("--catalog", default=str(ROOT / "faults" / "host1.yaml"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("ids", nargs="*")
    r.add_argument("--all", action="store_true")
    r.add_argument("--symptom-timeout", type=float, default=70)
    r.add_argument("--recover-timeout", type=float, default=120)
    r.add_argument("--out", default="data/runs")
    v = sub.add_parser("revert")
    v.add_argument("id")
    p = sub.add_parser("plan")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--trials", type=int, default=5)
    p.add_argument("--out", default="data/benchmark_plan.csv")
    args = ap.parse_args()
    from contextlib import nullcontext
    from lab_lock import lab_lock, LabBusy
    if args.cmd in ('run', 'revert'):
        load_catalog(args.catalog)
    try:
        with lab_lock(LAB) if args.cmd in ('run', 'revert') else nullcontext():
            {"list": cmd_list, "run": cmd_run, "plan": cmd_plan, "revert": cmd_revert}[args.cmd](args)
    except LabBusy as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
