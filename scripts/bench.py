#!/usr/bin/env python3
# Menjalankan jadwal benchmark: inject fault, tunggu gejala, minta diagnosis ke API live Host 1,
# cek evidence dan linter, lalu revert katalog dan pastikan lab balik normal.
# Tahap sekarang masih read-only: perintah usulan agen gak pernah diterapkan (applied selalu false).
#
#   export LIVE_API_TOKEN=...       # token dari environment, jangan ditulis ke file
#   python3 scripts/bench.py --api http://127.0.0.1:8766 --out data/host2/pilot --faults F01,F16,F22 --trials 1
#   python3 scripts/bench.py --api ... --out data/host2/pilot --retry 12     # ulang baris jadwal 12 secara eksplisit
#   python3 scripts/bench.py --api ... --out data/host2/mock-test --no-lab --limit 5   # uji client ke mock saja
#
# Hasil final ada di <out>/results.jsonl (satu baris per baris jadwal per attempt), kejadian
# perantara (request tersimpan, hasil telat, run terputus) di <out>/journal.jsonl.
# Exit code: 0 selesai, 1 gagal mulai (API gak bisa dihubungi, mode simulasi tanpa --no-lab), 2 dihentikan
# karena error/respons gak valid/lab gak pulih, 4 ada job yang belum jelas selesai dan fault sengaja ditahan.
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fault_runner as fr  # noqa: E402
import live_client as lc  # noqa: E402
from check_lab import check  # noqa: E402


STOP_STATUS = {"error", "admission_error", "invalid_response", "evidence_error"}


class Stop(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path, value):
    with path.open("a") as fh:
        fh.write(json.dumps(value, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def load_plan(path, faults, trials, limit):
    with open(path, newline="") as fh:
        rows = [{"order": int(r["order"]), "fault_id": r["fault_id"], "variant": r["variant"], "trial": int(r["trial"])}
                for r in csv.DictReader(fh)]
    if faults:
        rows = [r for r in rows if r["fault_id"] in faults]
    if trials:
        rows = [r for r in rows if r["trial"] <= trials]
    return rows[:limit] if limit else rows


def run_lint(commands):
    if not commands:
        return {"status": "not_requested", "violations": [], "commands_sha256": None}
    out = {"commands_sha256": lc.canonical_sha256(commands), "linter": "rca.linter"}
    try:
        sys.path.insert(0, str(fr.ROOT))
        from rca import linter
        res = linter.lint(commands)
        out.update(status="passed" if res["passed"] else "rejected", violations=res["violations"],
                   policy_version=getattr(linter, "POLICY_VERSION", None))
    except Exception as e:
        out.update(status="error", violations=[], message=f"{type(e).__name__}: {e}")
    return out


class Bench:
    def __init__(self, args, client, faults, catalog_sha):
        self.args, self.client, self.faults, self.catalog_sha = args, client, faults, catalog_sha
        self.out = Path(args.out)
        self.results = self.out / "results.jsonl"
        self.journal = self.out / "journal.jsonl"
        self.base_routes = None

    def baseline_ok(self):
        snap = check(fr.LAB)
        diff = fr.route_diff(self.base_routes, fr.loopback_routes()) if self.base_routes else []
        return snap["failures"] + diff

    # Mengecek API siap dan gak ada job lain sebelum inject, biar fault gak dipasang percuma.
    def wait_idle(self):
        for _ in range(30):
            health = self.client.health()
            if health.get("ready") is False:
                raise Stop(2, "API belum ready, fault gak di-inject")
            if not health.get("active"):
                return
            time.sleep(1)
        raise Stop(2, "API masih active setelah 30 detik, ada job lain yang jalan")

    # Membereskan baris yang terputus di sesi sebelumnya: cari job-nya lewat request_id, catat, lalu
    # tandai interrupted. Gak diulang otomatis, harus lewat --retry biar attempt ulangnya tercatat.
    def reconcile(self):
        interrupted = []
        finals = {(r["plan_order"], r["attempt"]) for r in read_jsonl(self.results)}
        pending = {}
        for ev in read_jsonl(self.journal):
            key = (ev["plan_order"], ev["attempt"])
            if key not in finals:
                pending.setdefault(key, {}).update({k: v for k, v in ev.items() if v is not None})
        for (order, attempt), ev in sorted(pending.items()):
            job = None
            if ev.get("request"):
                job = self.client.job_by_request(ev["request"]["request_id"])
                if job is not None:
                    job, done = lc.wait_terminal(self.client, job, time.monotonic() + self.args.reconcile)
                    if not done:
                        raise Stop(4, f"Job baris {order} masih {job.get('state')}, tunggu sampai selesai dulu")
            rec = new_record(order, attempt, ev.get("fault_id"), ev.get("variant"), ev.get("trial"),
                             ev.get("catalog_sha256"))
            rec.update(request_id=(ev.get("request") or {}).get("request_id"), job_id=job and job.get("job_id"),
                       status="interrupted_runner", diagnosis=job, recovered=None,
                       error="runner berhenti di tengah baris ini, kondisi lab saat itu gak tercatat")
            append_jsonl(self.results, rec)
            print(f"[{order}] ditandai interrupted_runner dari sesi sebelumnya")
            interrupted.append(ev.get("fault_id"))
        return interrupted

    def run_row(self, row, attempt):
        fault = self.faults[row["fault_id"]]
        rec = new_record(row["order"], attempt, row["fault_id"], row["variant"], row["trial"], self.catalog_sha)
        points = {}
        origin = time.monotonic()

        def mark(name):
            points[name] = {"utc": lc.utc_now(), "elapsed_s": round(time.monotonic() - origin, 3)}

        append_jsonl(self.journal, {"event": "start", "plan_order": row["order"], "attempt": attempt,
                                    "fault_id": row["fault_id"], "variant": row["variant"], "trial": row["trial"],
                                    "catalog_sha256": self.catalog_sha})
        # post_sent: request mungkin udah sampai server. Sejak itu, selama job belum jelas terminal,
        # lab gak boleh disentuh (revert/inject) karena server bisa lagi ngambil evidence.
        post_sent, terminal, hold_fault = False, False, False
        try:
            mark("t_inject")
            if self.args.no_lab:
                seen = ["no_lab: fault gak di-inject, cuma uji client"]
            else:
                fr.apply_steps(fault["inject"]["router"], fault["inject"]["steps"])
                seen, _ = fr.wait_for(lambda: fr.symptoms(self.base_routes)[1], self.args.symptom_timeout, interval=2)
            rec["symptoms"] = seen or []
            if not seen:
                rec["status"] = "not_observable"
                return rec
            mark("t_symptom")
            request = lc.new_request(row["variant"], points["t_symptom"]["utc"], fr.LAB)
            rec["request_id"] = request["request_id"]
            append_jsonl(self.journal, {"event": "request", "plan_order": row["order"], "attempt": attempt,
                                        "request": request})
            mark("t_request")
            deadline = time.monotonic() + self.args.budget
            post_sent = True
            job = self.submit(request)
            if job is None:
                post_sent = False
                rec["status"] = "admission_error"
                rec["error"] = "request ditolak server, job gak pernah dibuat"
                return rec
            rec["job_id"] = job.get("job_id")
            job, done = lc.wait_terminal(self.client, job, deadline)
            rec["diagnosis"] = job
            if not done:
                rec["status"], rec["completion_unknown"] = "timeout", True
                late, done = lc.wait_terminal(self.client, job, time.monotonic() + self.args.reconcile)
                if done:
                    terminal = True
                    append_jsonl(self.journal, {"event": "late_result", "plan_order": row["order"],
                                                "attempt": attempt, "job": late})
                else:
                    hold_fault = True
                return rec
            terminal = True
            mark("t_diagnosis_done")
            problems = lc.validate_job(job, request, rec["job_id"], allow_simulation=self.args.no_lab)
            problems += schema_problems(job)
            if problems:
                rec["status"], rec["error"] = "invalid_response", "; ".join(problems)
                return rec
            rec["status"] = {"completed": "completed", "failed": "job_failed"}.get(job["state"], "job_interrupted")
            if job["state"] != "completed":
                return rec
            t = time.monotonic()
            rec["evidence_check"] = lc.verify_evidence(self.client, job)
            rec["evidence_check"]["fetch_seconds"] = round(time.monotonic() - t, 3)
            if rec["evidence_check"]["problems"]:
                # Menghentikan pipeline di sini, perintah dari evidence yang gak cocok gak di-lint.
                rec["status"] = "evidence_error"
                rec["error"] = "; ".join(rec["evidence_check"]["problems"])
                return rec
            rec["lint"] = run_lint(job["assessment"]["commands"])
            mark("t_lint_done")
            return rec
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
            if post_sent and not terminal:
                rec["status"], rec["completion_unknown"] = "completion_unknown", True
                hold_fault = True
            else:
                rec["status"] = "error"
            return rec
        finally:
            if self.args.no_lab:
                rec["fallback_revert"] = {"performed": False, "reason": "no_lab"}
                rec["recovered"] = None
            elif hold_fault:
                # Menahan fault karena job belum jelas selesai, revert sekarang bisa bentrok sama capture evidence.
                rec["fallback_revert"] = {"performed": False, "reason": "job_unresolved"}
            else:
                mark("t_revert")
                res = fr.revert_and_verify(fault, self.base_routes, self.args.recover_timeout)
                rec["fallback_revert"] = {"performed": True, "reason": "read_only_phase",
                                          "error": res["revert_error"]}
                rec["recovered"] = res["recovered"]
                if res["recovered"]:
                    mark("t_verified")
                rec["verification"] = {"source": "catalog_revert", "checks_passed": res["recovered"]}
            rec["timing"] = timing(points)

    # Mengirim request. Hasilnya job, atau None kalau server jelas nolak (admission) dan job gak tersimpan.
    # Error lain setelah POST dicek ulang lewat request_id sampai batas --reconcile.
    def submit(self, request):
        try:
            return lc.submit_once(self.client, request)
        except lc.ApiError as e:
            if e.status < 500 or e.code in lc.ADMISSION_CODES:
                return None
        except lc.TRANSPORT_ERRORS:
            pass
        deadline = time.monotonic() + self.args.reconcile
        while time.monotonic() < deadline:
            try:
                job = self.client.job_by_request(request["request_id"])
            except (lc.ApiError, *lc.TRANSPORT_ERRORS):
                time.sleep(2)
                continue
            return job
        raise RuntimeError("status request gak bisa dipastikan sampai batas reconcile")

    def run(self, rows):
        self.out.mkdir(parents=True, exist_ok=True)
        interrupted = self.reconcile()
        problems = [] if self.args.no_lab else self.baseline_ok()
        if problems:
            hint = "".join(f"\nFault {f} mungkin masih kepasang: python3 scripts/fault_runner.py revert {f}"
                           for f in interrupted if f)
            raise Stop(2, "Baseline tidak sehat:\n  " + "\n  ".join(problems) + hint)
        self.base_routes = None if self.args.no_lab else fr.loopback_routes()

        attempts = {}
        for r in read_jsonl(self.results):
            attempts[r["plan_order"]] = max(attempts.get(r["plan_order"], 0), r["attempt"])
        todo = [(r, attempts.get(r["order"], 0) + 1) for r in rows
                if r["order"] not in attempts or r["order"] in self.args.retry]
        print(f"{len(todo)} baris dijalankan, {len(rows) - len(todo)} sudah ada hasilnya")

        for row, attempt in todo:
            self.wait_idle()
            problems = [] if self.args.no_lab else self.baseline_ok()
            if problems:
                raise Stop(2, f"Baseline berubah sebelum baris {row['order']}:\n  " + "\n  ".join(problems))
            rec = self.run_row(row, attempt)
            append_jsonl(self.results, rec)
            result = ((rec["diagnosis"] or {}).get("result") or {}).get("status")
            lint = (rec["lint"] or {}).get("status")
            t = rec["timing"]
            print(f"[{row['order']}] {row['fault_id']} {row['variant']:<9} {rec['status']:<16} "
                  f"hasil={result or '-'} lint={lint or '-'} diagnosis={fmt(t.get('diagnosis_s'))} "
                  f"pulih={rec['recovered']}", flush=True)
            if rec["error"]:
                print(f"    error: {rec['error']}")
            if rec["fallback_revert"]["reason"] == "job_unresolved":
                raise Stop(4, f"Job baris {row['order']} belum selesai, fault {row['fault_id']} sengaja dibiarkan. "
                              f"Setelah job selesai jalankan: python3 scripts/fault_runner.py revert {row['fault_id']}")
            if rec["status"] in STOP_STATUS or rec["recovered"] is False:
                raise Stop(2, f"Baris {row['order']} berhenti dengan status {rec['status']}, cek lab sebelum lanjut")
        print(f"Hasil: {self.results}")


# Memvalidasi job pakai model pydantic milik Host 1 kalau bisa di-import, kalau gak ada cek manual di
# live_client tetap jalan.
def schema_problems(job):
    sys.path.insert(0, str(fr.ROOT / "host1"))
    try:
        from live_api.models import Job
    except ImportError:
        return []
    try:
        Job.model_validate(job)
    except Exception as e:
        return [f"schema: {str(e).splitlines()[0]}"]
    return []


def new_record(order, attempt, fault_id, variant, trial, catalog_sha):
    return {"plan_order": order, "attempt": attempt, "fault_id": fault_id, "variant": variant, "trial": trial,
            "catalog_sha256": catalog_sha, "request_id": None, "job_id": None, "status": None, "symptoms": [],
            "diagnosis": None, "evidence_check": None, "lint": None, "applied": False, "execution": None,
            "verification": None, "fallback_revert": {"performed": False, "reason": None}, "recovered": False,
            "completion_unknown": False, "error": None, "timing": None}


# Menyimpan tiap titik waktu sebagai {utc, elapsed_s}. elapsed_s monotonic dari awal baris, UTC buat korelasi.
def timing(points):
    def span(a, b):
        return round(points[b]["elapsed_s"] - points[a]["elapsed_s"], 3) if a in points and b in points else None
    names = ("t_inject", "t_symptom", "t_request", "t_diagnosis_done", "t_lint_done", "t_apply_done", "t_revert",
             "t_verified")
    return {**{n: points.get(n) for n in names}, "detection_s": span("t_inject", "t_symptom"),
            "diagnosis_s": span("t_symptom", "t_diagnosis_done"), "job_wait_s": span("t_request", "t_diagnosis_done"),
            "fallback_recovery_s": span("t_revert", "t_verified"), "agent_recovery_s": None}


def fmt(v):
    return "-" if v is None else f"{v:.1f}s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True, help="root URL API live, misalnya http://127.0.0.1:8766")
    ap.add_argument("--out", required=True, help="folder sesi, misalnya data/host2/pilot")
    ap.add_argument("--catalog", default=str(fr.ROOT / "faults" / "host1.yaml"))
    ap.add_argument("--plan", default=str(fr.ROOT / "data" / "benchmark_plan.csv"))
    ap.add_argument("--faults", type=lambda s: set(s.split(",")), default=None)
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retry", type=int, nargs="*", default=[])
    ap.add_argument("--budget", type=float, default=180, help="batas tunggu diagnosis per job, detik")
    ap.add_argument("--reconcile", type=float, default=600, help="batas tunggu tambahan untuk job yang telat")
    ap.add_argument("--no-lab", action="store_true",
                    help="uji client ke mock tanpa inject/revert dan tanpa menyentuh lab")
    ap.add_argument("--symptom-timeout", type=float, default=70)
    ap.add_argument("--recover-timeout", type=float, default=120)
    args = ap.parse_args()

    faults = {f["id"]: f for f in fr.load_catalog(args.catalog)}
    catalog_sha = hashlib.sha256(Path(args.catalog).read_bytes()).hexdigest()
    rows = load_plan(args.plan, args.faults, args.trials, args.limit)
    unknown = {r["fault_id"] for r in rows} - set(faults)
    if unknown:
        sys.exit(f"Fault di jadwal gak ada di katalog: {', '.join(sorted(unknown))}")

    try:
        client = lc.LiveClient(args.api, os.environ.get("LIVE_API_TOKEN", ""))
        caps = client.capabilities()
    except (ValueError, lc.ApiError, *lc.TRANSPORT_ERRORS) as e:
        sys.exit(f"Gagal menghubungi API: {e}")
    missing = {r["variant"] for r in rows} - set(caps.get("variants") or [])
    if missing:
        sys.exit(f"Varian belum tersedia di API: {', '.join(sorted(missing))}")
    simulated = caps.get("simulation") is not False or caps.get("mode") != "live"
    if simulated and not args.no_lab:
        sys.exit(f"API berjalan dalam mode {caps.get('mode')} (simulasi). Lab gak disentuh, pakai --no-lab "
                 "kalau cuma mau uji client")
    if simulated:
        print(f"Catatan: API berjalan dalam mode {caps.get('mode')}, hasil diagnosis bukan dari agen sungguhan")

    try:
        Bench(args, client, faults, catalog_sha).run(rows)
    except Stop as e:
        print(str(e))
        sys.exit(e.code)


if __name__ == "__main__":
    main()
