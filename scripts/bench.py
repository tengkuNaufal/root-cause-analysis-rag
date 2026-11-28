#!/usr/bin/env python3
# Menjalankan jadwal benchmark: inject fault, tunggu gejala, minta diagnosis ke API live Host 1,
# cek evidence dan linter, lalu revert katalog dan pastikan lab balik normal.
# Default-nya read-only (applied false). Dengan --execute, perintah agen yang lolos linter diterapkan lalu
# diverifikasi; kalau lab gak pulih, runner fallback ke revert katalog dan reset konfigurasi ke baseline.
#
#   export LIVE_API_TOKEN=...       # token dari environment, jangan ditulis ke file
#   python3 scripts/bench.py --api http://127.0.0.1:8766 --out data/host2/pilot --faults F01,F16,F22 --trials 1
#   python3 scripts/bench.py --api ... --out data/host2/smoke --execute --faults F01 --variants graph_rag --trials 1
#   python3 scripts/bench.py --out data/host2/regex --execute --variants rule_based   # pembanding regex, tanpa API
#   python3 scripts/bench.py --api ... --out data/host2/pilot --retry 12     # ulang baris jadwal 12 secara eksplisit
#   python3 scripts/bench.py --api ... --out data/host2/mock-test --no-lab --limit 5   # uji client ke mock saja
#   python3 scripts/bench.py --api ... --out data/host2/pilot --release 12   # lepas baris 12 setelah dipastikan job-nya gak ada
#
# Hasil final ada di <out>/results.jsonl (satu baris per baris jadwal per attempt), kejadian
# perantara (request tersimpan, hasil telat, run terputus) di <out>/journal.jsonl.
# Exit code: 0 selesai, 1 gagal mulai (API gak bisa dihubungi, mode simulasi tanpa --no-lab, lab lagi dipakai
# proses bench lain), 2 dihentikan karena error/respons gak valid/lab gak pulih, 4 ada job yang belum jelas selesai
# dan fault sengaja ditahan.
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
import regex_baseline as rb  # noqa: E402
from check_lab import check  # noqa: E402
from lab_lock import lab_lock, LabBusy


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


def load_plan(path, faults, trials, limit, variants=None):
    with open(path, newline="") as fh:
        rows = [{"order": int(r["order"]), "fault_id": r["fault_id"], "variant": r["variant"], "trial": int(r["trial"])}
                for r in csv.DictReader(fh)]
    if faults:
        rows = [r for r in rows if r["fault_id"] in faults]
    if trials:
        rows = [r for r in rows if r["trial"] <= trials]
    if variants:
        rows = [r for r in rows if r["variant"] in variants]
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


# Dipakai saat job mungkin udah diterima server tapi belum jelas terminal: lab ditahan apa adanya.
class Held(Exception):
    pass


class Bench:
    def __init__(self, args, client, faults, catalog_sha):
        self.args, self.client, self.faults, self.catalog_sha = args, client, faults, catalog_sha
        self.out = Path(args.out)
        self.results = self.out / "results.jsonl"
        self.journal = self.out / "journal.jsonl"
        self.baseline_file = self.out / "baseline_routes.json"
        self.config_file = self.out / "baseline_configs.json"
        self.base_routes = None
        self.base_configs = None

    def baseline_ok(self):
        snap = check(fr.LAB)
        diff = fr.route_diff(self.base_routes, fr.loopback_routes()) if self.base_routes else []
        return snap["failures"] + diff + [f"{r}: konfigurasi FRR beda dengan baseline" for r in self.config_drift()]

    def config_drift(self):
        if not self.base_configs:
            return []
        now = fr.config_digests()
        return sorted(r for r in self.base_configs if now.get(r) != self.base_configs[r])

    # Mengembalikan lab ke baseline: revert katalog, lalu router yang konfigurasinya beda (atau semua
    # router kalau lab masih belum sehat) di-reset ke startup-config. Perubahan dari agen yang salah
    # sasaran ikut kebersihkan di sini, jadi baris berikutnya mulai dari kondisi yang sama.
    def restore(self, fault, reason):
        res = fr.revert_and_verify(fault, self.base_routes, self.args.recover_timeout)
        out = {"performed": True, "reason": reason, "error": res["revert_error"], "reset_routers": []}
        drift = self.config_drift()
        # Mereset router yang konfigurasinya beda dulu, baru semua router kalau lab masih belum sehat.
        for routers in (drift, sorted(fr.EXPECTED[fr.LAB])):
            if res["recovered"] and not self.config_drift():
                break
            if not routers:
                continue
            out["reset_routers"] = routers
            for r in routers:
                try:
                    fr.reset_router(r)
                except Exception as e:
                    out["error"] = f"reset {r}: {e}"
            healthy, _ = fr.wait_for(lambda: not fr.symptoms(self.base_routes)[1], self.args.recover_timeout,
                                     interval=2)
            res["recovered"] = bool(healthy)
        out["recovered"] = res["recovered"] and not self.config_drift()
        return out

    # Menerapkan perintah agen yang lolos linter. Sebelum jalan, hash perintah dicek sama dengan yang
    # di-lint dan gejala fault harus masih ada; kalau lab udah berubah, perintah gak diterapkan.
    def execute(self, rec, job, mark):
        commands = job["assessment"]["commands"]
        ex = {"attempted": False, "skipped_reason": None, "commands_sha256": rec["lint"]["commands_sha256"],
              "results": [], "agent_recovered": False}
        rec["execution"] = ex
        if lc.canonical_sha256(commands) != rec["lint"]["commands_sha256"]:
            ex["skipped_reason"] = "commands_changed_after_lint"
            return
        if not fr.symptoms(self.base_routes)[1]:
            ex["skipped_reason"] = "precondition_changed"
            return
        ex["attempted"] = True
        for i, c in enumerate(commands):
            argv = ["ip", *c["args"]] if c["interpreter"] == "ip" else fr.vtysh_argv(c["args"])
            try:
                fr.run_argv(c["router"], argv)
                ex["results"].append({"index": i, "ok": True})
            except Exception as e:
                ex["results"].append({"index": i, "ok": False, "error": str(e)[:300]})
                break
        rec["applied"] = True
        mark("t_apply_done")
        if all(r["ok"] for r in ex["results"]):
            healthy, _ = fr.wait_for(lambda: not fr.symptoms(self.base_routes)[1],
                                     self.args.agent_verify_timeout, interval=1)
            if healthy:
                mark("t_verified")
                ex["agent_recovered"] = True

    # Mengecek API siap dan gak ada job lain sebelum inject, biar fault gak dipasang percuma.
    def wait_idle(self):
        if self.client is None:
            return
        for _ in range(30):
            health = self.client.health()
            if health.get("ready") is False:
                raise Stop(2, "API belum ready, fault gak di-inject")
            if not health.get("active"):
                return
            time.sleep(1)
        raise Stop(2, "API masih active setelah 30 detik, ada job lain yang jalan")

    def log(self, event, order, attempt, **fields):
        append_jsonl(self.journal, {"event": event, "plan_order": order, "attempt": attempt, **fields})

    # Membereskan baris yang belum punya hasil final dari sesi sebelumnya (runner mati, Ctrl+C, atau
    # job yang ditahan). Job dicari lewat request_id dan harus terminal dulu, baru fault-nya di-revert.
    # Kalau job gak ketemu, runner gak menganggapnya ditolak: operator harus memastikan ke Host 1 lalu
    # memakai --release ORDER. Baris ini gak diulang otomatis, ulangi lewat --retry.
    def reconcile(self):
        finals = {(r["plan_order"], r["attempt"]) for r in read_jsonl(self.results)}
        pending = {}
        for ev in read_jsonl(self.journal):
            key = (ev["plan_order"], ev["attempt"])
            if key not in finals:
                pending.setdefault(key, {}).update({k: v for k, v in ev.items() if v is not None})
        for (order, attempt), ev in sorted(pending.items()):
            job = None
            request = ev.get("request")
            if request:
                try:
                    job = self.client.job_by_request(request["request_id"])
                except (lc.ApiError, *lc.TRANSPORT_ERRORS) as e:
                    raise Stop(4, f"Gagal mengecek job baris {order} ({e}), lab dibiarkan") from None
                if job is None and order not in self.args.release:
                    raise Stop(4, f"Job baris {order} (request {request['request_id']}) belum terlihat di server. "
                                  f"Lab dibiarkan. Pastikan ke Host 1 job ini gak ada, lalu jalankan ulang dengan "
                                  f"--release {order}")
                if job is not None:
                    job, done = lc.wait_terminal(self.client, job, time.monotonic() + self.args.reconcile)
                    if not done:
                        raise Stop(4, f"Job baris {order} masih {job.get('state')}, lab dibiarkan. Coba lagi nanti")
            rec = new_record(order, attempt, ev.get("fault_id"), ev.get("variant"), ev.get("trial"),
                             ev.get("catalog_sha256"))
            rec.update(request_id=(request or {}).get("request_id"), job_id=job and job.get("job_id"),
                       status=ev.get("held_status", "interrupted_runner"), diagnosis=job,
                       completion_unknown=job is None and bool(request),
                       error=ev.get("reason", "runner berhenti di tengah baris ini"))
            fault = self.faults.get(ev.get("fault_id"))
            if fault and not self.args.no_lab:
                res = self.restore(fault, "reconcile")
                rec["fallback_revert"] = res
                rec["recovered"] = res["recovered"]
                rec["verification"] = {"source": "catalog_revert", "checks_passed": res["recovered"]}
            else:
                rec["recovered"] = None
            append_jsonl(self.results, rec)
            print(f"[{order}] dibereskan dari sesi sebelumnya: {rec['status']}, pulih={rec['recovered']}")

    def run_row(self, row, attempt):
        fault = self.faults[row["fault_id"]]
        order = row["order"]
        rec = new_record(order, attempt, row["fault_id"], row["variant"], row["trial"], self.catalog_sha)
        points = {}
        origin = time.monotonic()

        def mark(name):
            points[name] = {"utc": lc.utc_now(), "elapsed_s": round(time.monotonic() - origin, 3)}

        self.log("start", order, attempt, fault_id=row["fault_id"], variant=row["variant"], trial=row["trial"],
                 catalog_sha256=self.catalog_sha)
        # post_sent: request mungkin udah sampai server. Sejak itu, selama job belum jelas terminal,
        # lab gak boleh disentuh (revert/inject) karena server bisa lagi ngambil evidence.
        post_sent, terminal = False, False
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
            if row["variant"] == rb.VARIANT:
                # Menjalankan pembanding regex lokal di runner, gak lewat API jadi gak ada job yang perlu ditahan.
                mark("t_request")
                snap = rb.collect(sorted(fr.EXPECTED[fr.LAB]), points["t_inject"]["utc"])
                job = rb.make_job(request, snap)
                mark("t_diagnosis_done")
                n = len(job["evidence"])
                rec.update(job_id=job["job_id"], diagnosis=job, status="completed",
                           evidence_check={"total": n, "verified": n, "problems": [], "source": "local"})
                rec["lint"] = run_lint(job["assessment"]["commands"])
                mark("t_lint_done")
                if self.args.execute and rec["lint"]["status"] == "passed":
                    self.execute(rec, job, mark)
                return rec
            self.log("request", order, attempt, request=request)
            mark("t_request")
            deadline = time.monotonic() + self.args.budget
            post_sent = True
            job = self.submit(request)
            if job is None:
                post_sent = False
                rec["status"], rec["error"] = "admission_error", "request ditolak server, job gak pernah dibuat"
                return rec
            rec["job_id"] = job.get("job_id")
            self.log("job", order, attempt, job_id=rec["job_id"])
            job, done = lc.wait_terminal(self.client, job, deadline)
            rec["diagnosis"] = job
            if not done:
                late, done = lc.wait_terminal(self.client, job, time.monotonic() + self.args.reconcile)
                if not done:
                    raise Held("timeout", "job belum terminal setelah batas tunggu dan reconcile")
                terminal = True
                rec["status"], rec["completion_unknown"] = "timeout", True
                self.log("late_result", order, attempt, job=late)
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
            rejection = lc.read_rejection(job)
            rec["proposal"] = rejection or {"status": "available" if job["assessment"]["commands"] else "not_proposed"}
            if rejection:
                # No exported command is available to lint or execute. Preserve server rejection separately.
                rec["lint"] = {"status": "not_requested", "violations": [], "commands_sha256": None,
                               "reason": "api_proposal_rejected"}
                rec["execution"] = {"attempted": False, "skipped_reason": "api_proposal_rejected",
                                    "commands_sha256": None, "results": [], "agent_recovered": False}
                mark("t_lint_done")
                return rec
            rec["lint"] = run_lint(job["assessment"]["commands"])
            mark("t_lint_done")
            if self.args.execute and rec["lint"]["status"] == "passed":
                self.execute(rec, job, mark)
            return rec
        except BaseException as e:
            if post_sent and not terminal:
                # Menyimpan checkpoint lalu menahan lab. Hasil final baru ditulis saat resume.
                status, reason = e.args if isinstance(e, Held) else ("completion_unknown", f"{type(e).__name__}: {e}")
                self.log("held", order, attempt, request_id=rec["request_id"], job_id=rec["job_id"],
                         held_status=status, reason=reason)
                raise Held(status, reason) if not isinstance(e, Held) else e
            rec["status"] = "interrupted_operator" if isinstance(e, KeyboardInterrupt) else "error"
            rec["error"] = f"{type(e).__name__}: {e}"
            if isinstance(e, KeyboardInterrupt):
                self.finish(rec, fault, mark, points)
                append_jsonl(self.results, rec)
                raise
            return rec
        finally:
            if rec["status"] not in (None, "interrupted_operator") and rec["timing"] is None:
                self.finish(rec, fault, mark, points)

    def finish(self, rec, fault, mark, points):
        if self.args.no_lab:
            rec["fallback_revert"] = {"performed": False, "reason": "no_lab"}
            rec["recovered"] = None
        elif (rec["execution"] or {}).get("agent_recovered"):
            rec["recovered"] = True
            rec["verification"] = {"source": "agent", "checks_passed": True}
            rec["fallback_revert"] = {"performed": False, "reason": "agent_recovered"}
            # Membersihkan sisa perubahan agen yang beda dari baseline, gak dihitung sebagai fallback.
            if self.config_drift():
                rec["cleanup"] = self.restore(fault, "cleanup_after_agent")
                if not rec["cleanup"]["recovered"]:
                    rec["recovered"] = False
        else:
            mark("t_revert")
            reason = "agent_fix_failed" if (rec["execution"] or {}).get("attempted") else "read_only_phase"
            if (rec.get("proposal") or {}).get("status") == "rejected":
                reason = "api_proposal_rejected"
            res = self.restore(fault, reason)
            rec["fallback_revert"] = res
            rec["recovered"] = res["recovered"]
            if res["recovered"]:
                mark("t_fallback_verified")
            rec["verification"] = {"source": "catalog_revert", "checks_passed": res["recovered"]}
        rec["timing"] = timing(points)

    # Mengirim request. Hasilnya job, atau None hanya kalau POST pertama dapat penolakan yang pasti dari
    # server (4xx atau kode admission). Selain itu request mungkin udah diterima, jadi job dicari lewat
    # request_id sampai batas --reconcile tanpa POST ulang. 404 di sini belum berarti ditolak.
    def submit(self, request):
        try:
            return self.client.submit(request)
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
                job = None
            if job is not None:
                return job
            time.sleep(self.args.lookup_interval)
        raise Held("completion_unknown", "request mungkin terkirim tapi job gak terlihat sampai batas reconcile")

    def run(self, rows):
        self.out.mkdir(parents=True, exist_ok=True)
        # Memakai tabel rute baseline yang disimpan di sesi pertama, biar pengecekan setelah resume
        # gak membandingkan dengan kondisi lab yang mungkin masih rusak.
        if self.baseline_file.exists():
            self.base_routes = json.loads(self.baseline_file.read_text())
        if self.config_file.exists():
            self.base_configs = json.loads(self.config_file.read_text())
        self.reconcile()
        if not self.args.no_lab:
            problems = self.baseline_ok()
            if problems:
                raise Stop(2, "Baseline tidak sehat:\n  " + "\n  ".join(problems))
            if self.base_routes is None:
                self.base_routes = fr.loopback_routes()
                self.baseline_file.write_text(json.dumps(self.base_routes))
            if self.base_configs is None:
                self.base_configs = fr.config_digests()
                self.config_file.write_text(json.dumps(self.base_configs))

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
            try:
                rec = self.run_row(row, attempt)
            except Held as e:
                raise Stop(4, f"Baris {row['order']}: {e.args[1]}. Fault {row['fault_id']} sengaja dibiarkan dan "
                              f"belum ada hasil final. Jalankan ulang perintah yang sama untuk merekonsiliasi job "
                              f"ini sebelum lanjut.") from None
            append_jsonl(self.results, rec)
            result = ((rec["diagnosis"] or {}).get("result") or {}).get("status")
            lint = (rec["lint"] or {}).get("status")
            print(f"[{row['order']}] {row['fault_id']} {row['variant']:<9} {rec['status']:<16} "
                  f"hasil={result or '-'} lint={lint or '-'} diagnosis={fmt(rec['timing'].get('diagnosis_s'))} "
                  f"agen_pulihkan={fmt(rec['timing'].get('agent_recovery_s'))} pulih={rec['recovered']}", flush=True)
            if rec["error"]:
                print(f"    error: {rec['error']}")
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
            "diagnosis": None, "evidence_check": None, "proposal": None, "lint": None, "applied": False, "execution": None,
            "cleanup": None,
            "verification": None, "fallback_revert": {"performed": False, "reason": None}, "recovered": False,
            "completion_unknown": False, "error": None, "timing": None}


# Menyimpan tiap titik waktu sebagai {utc, elapsed_s}. elapsed_s monotonic dari awal baris, UTC buat korelasi.
def timing(points):
    def span(a, b):
        return round(points[b]["elapsed_s"] - points[a]["elapsed_s"], 3) if a in points and b in points else None
    names = ("t_inject", "t_symptom", "t_request", "t_diagnosis_done", "t_lint_done", "t_apply_done", "t_verified",
             "t_revert", "t_fallback_verified")
    return {**{n: points.get(n) for n in names}, "detection_s": span("t_inject", "t_symptom"),
            "diagnosis_s": span("t_symptom", "t_diagnosis_done"), "job_wait_s": span("t_request", "t_diagnosis_done"),
            "fallback_recovery_s": span("t_revert", "t_fallback_verified"),
            "agent_recovery_s": span("t_symptom", "t_verified")}


def fmt(v):
    return "-" if v is None else f"{v:.1f}s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", help="root URL API live, misalnya http://127.0.0.1:8766 (gak perlu kalau cuma "
                                  "varian rule_based)")
    ap.add_argument("--out", required=True, help="folder sesi, misalnya data/host2/pilot")
    ap.add_argument("--catalog", default=str(fr.ROOT / "faults" / "host1.yaml"))
    ap.add_argument("--plan", default=str(fr.ROOT / "data" / "benchmark_plan.csv"))
    ap.add_argument("--faults", type=lambda s: set(s.split(",")), default=None)
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retry", type=int, nargs="*", default=[])
    ap.add_argument("--release", type=int, nargs="*", default=[],
                    help="baris yang job-nya sudah dipastikan gak ada di Host 1, boleh direkonsiliasi tanpa job")
    ap.add_argument("--budget", type=float, default=180, help="batas tunggu diagnosis per job, detik")
    ap.add_argument("--reconcile", type=float, default=600, help="batas tunggu tambahan untuk job yang telat")
    ap.add_argument("--lookup-interval", type=float, default=2, help=argparse.SUPPRESS)
    ap.add_argument("--execute", action="store_true",
                    help="terapkan perintah agen yang lolos linter, lalu verifikasi; tanpa ini runner read-only")
    ap.add_argument("--agent-verify-timeout", type=float, default=60,
                    help="batas tunggu lab pulih setelah perintah agen diterapkan, detik")
    ap.add_argument("--variants", type=lambda s: set(s.split(",")), default=None)
    ap.add_argument("--no-lab", action="store_true",
                    help="uji client ke mock tanpa inject/revert dan tanpa menyentuh lab")
    ap.add_argument("--symptom-timeout", type=float, default=70)
    ap.add_argument("--recover-timeout", type=float, default=120)
    args = ap.parse_args()

    faults = {f["id"]: f for f in fr.load_catalog(args.catalog)}
    catalog_sha = hashlib.sha256(Path(args.catalog).read_bytes()).hexdigest()
    if args.execute and args.no_lab:
        sys.exit("--execute gak bisa dipakai bareng --no-lab")
    rows = load_plan(args.plan, args.faults, args.trials, args.limit, args.variants)
    unknown = {r["fault_id"] for r in rows} - set(faults)
    if unknown:
        sys.exit(f"Fault di jadwal gak ada di katalog: {', '.join(sorted(unknown))}")

    variants = {r["variant"] for r in rows}
    if args.no_lab and rb.VARIANT in variants:
        sys.exit(f"Varian {rb.VARIANT} baca teks langsung dari lab, gak bisa bareng --no-lab")
    if variants == {rb.VARIANT} and not args.api:
        client, caps = None, {"mode": "live", "simulation": False, "variants": []}
    elif not args.api:
        sys.exit("--api wajib untuk varian zero_shot, text_rag, dan graph_rag")
    else:
        try:
            client = lc.LiveClient(args.api, os.environ.get("LIVE_API_TOKEN", ""))
            caps = client.capabilities()
        except (ValueError, lc.ApiError, *lc.TRANSPORT_ERRORS) as e:
            sys.exit(f"Gagal menghubungi API: {e}")
    missing = variants - {rb.VARIANT} - set(caps.get("variants") or [])
    if missing:
        sys.exit(f"Varian belum tersedia di API: {', '.join(sorted(missing))}")
    simulated = caps.get("simulation") is not False or caps.get("mode") != "live"
    if simulated and not args.no_lab:
        sys.exit(f"API berjalan dalam mode {caps.get('mode')} (simulasi). Lab gak disentuh, pakai --no-lab "
                 "kalau cuma mau uji client")
    if simulated:
        print(f"Catatan: API berjalan dalam mode {caps.get('mode')}, hasil diagnosis bukan dari agen sungguhan")

    try:
        from contextlib import nullcontext
        with nullcontext() if args.no_lab else lab_lock(fr.LAB):
            Bench(args, client, faults, catalog_sha).run(rows)
    except LabBusy as e:
        sys.exit(str(e))
    except Stop as e:
        print(str(e))
        sys.exit(e.code)
    except KeyboardInterrupt:
        print("Dihentikan operator. Kalau ada baris yang ditahan, jalankan ulang perintah yang sama untuk "
              "merekonsiliasinya dulu.")
        sys.exit(130)


if __name__ == "__main__":
    main()
