# Tes regresi bench.py: selama penyelesaian job belum jelas, revert dan inject berikutnya gak boleh jalan.
# Lab dan API diganti tiruan, jadi tes ini gak butuh Docker atau server.
import copy
import json
import sys
import types
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bench  # noqa: E402
import fault_runner as fr  # noqa: E402
import live_client as lc  # noqa: E402

EXAMPLES = json.loads((ROOT / "host1" / "live_api" / "examples.json").read_text())
FAULTS = {f["id"]: f for f in fr.load_catalog(ROOT / "faults" / "host1.yaml")}
ROWS = [{"order": 1, "fault_id": "F01", "variant": "graph_rag", "trial": 1},
        {"order": 2, "fault_id": "F25", "variant": "zero_shot", "trial": 1}]


def live_job(request, state="completed"):
    base = EXAMPLES["hypothesis"] if state == "completed" else EXAMPLES["pending"]
    job = copy.deepcopy(base)
    job.update(request_id=request["request_id"], variant=request["variant"], simulation=False)
    if state == "completed":
        job["result"]["request_id"] = request["request_id"]
        job["provenance"]["synthetic"] = False
    return job


class FakeApi:
    def __init__(self, submit=None, poll=None, lookup=None):
        self.requests = []
        self._submit, self._poll, self._lookup = submit, poll, lookup

    def health(self):
        return {"ready": True, "active": False}

    def submit(self, request):
        self.requests.append(request)
        return self._submit(request) if self._submit else live_job(request)

    def job(self, job_id):
        return self._poll(self.requests[-1]) if self._poll else live_job(self.requests[-1])

    def job_by_request(self, request_id):
        req = next((r for r in self.requests if r["request_id"] == request_id), {"request_id": request_id,
                                                                                    "variant": "graph_rag"})
        return self._lookup(req) if self._lookup else None

    def evidence(self, url):
        return dict(EXAMPLES["evidence"])


@pytest.fixture
def lab(monkeypatch):
    events = []
    fr.LAB = "rca"

    def apply_steps(router, steps):
        fid = next(f["id"] for f in FAULTS.values() if f["inject"]["steps"] is steps or f["revert"]["steps"] is steps)
        events.append(("inject" if FAULTS[fid]["inject"]["steps"] is steps else "manual_revert", fid))

    def revert_and_verify(fault, base, timeout):
        events.append(("revert", fault["id"]))
        return {"revert_error": None, "recovered": True}

    def run_argv(router, argv):
        events.append(("exec", router, " ".join(argv)))
        if "gagal" in argv:
            raise RuntimeError("perintah gagal")
        return ""

    monkeypatch.setattr(fr, "apply_steps", apply_steps)
    monkeypatch.setattr(fr, "run_argv", run_argv)
    monkeypatch.setattr(fr, "symptoms", lambda base: ({}, ["gejala tiruan"]))
    monkeypatch.setattr(fr, "config_digests", lambda: {"r1": "a"})
    monkeypatch.setattr(fr, "reset_router", lambda r: events.append(("reset", r)))
    monkeypatch.setattr(fr, "revert_and_verify", revert_and_verify)
    monkeypatch.setattr(fr, "wait_for", lambda fn, timeout, interval=1.0: (["gejala tiruan"], 0.0))
    monkeypatch.setattr(fr, "loopback_routes", lambda: {})
    monkeypatch.setattr(fr, "route_diff", lambda a, b: [])
    monkeypatch.setattr(bench, "check", lambda lab: {"failures": []})
    monkeypatch.setattr(bench, "schema_problems", lambda job: [])
    monkeypatch.setattr(lc.time, "sleep", lambda s: None)
    return events


def make(tmp_path, api, **over):
    args = types.SimpleNamespace(no_lab=False, budget=5, reconcile=0.05, lookup_interval=0, symptom_timeout=5,
                                 recover_timeout=5, out=str(tmp_path), retry=[], release=[], execute=False,
                                 agent_verify_timeout=5)
    for k, v in over.items():
        setattr(args, k, v)
    return bench.Bench(args, api, FAULTS, "sha")


def results(tmp_path):
    return bench.read_jsonl(tmp_path / "results.jsonl")


def journal_events(tmp_path):
    return [e["event"] for e in bench.read_jsonl(tmp_path / "journal.jsonl")]


def lost_post(request):
    raise urllib.error.URLError("connection reset")


def test_lookup_404_after_lost_post_holds_lab(tmp_path, lab):
    api = FakeApi(submit=lost_post)
    with pytest.raises(bench.Stop) as stop:
        make(tmp_path, api).run(ROWS)
    assert stop.value.code == 4
    assert lab == [("inject", "F01")]
    assert results(tmp_path) == []
    assert "held" in journal_events(tmp_path)

    # Resume: job ternyata ada dan sudah selesai, baru setelah itu F01 di-revert lalu baris 2 jalan.
    api._lookup = live_job
    api._submit = None
    make(tmp_path, api).run(ROWS)
    assert lab == [("inject", "F01"), ("revert", "F01"), ("inject", "F25"), ("revert", "F25")]
    rows = results(tmp_path)
    assert [r["plan_order"] for r in rows] == [1, 2]
    assert rows[0]["status"] == "completion_unknown" and rows[0]["diagnosis"]["state"] == "completed"


def test_server_error_on_post_is_not_treated_as_rejection(tmp_path, lab):
    def fail(request):
        raise lc.ApiError(500, "internal_error")

    with pytest.raises(bench.Stop) as stop:
        make(tmp_path, FakeApi(submit=fail)).run(ROWS)
    assert stop.value.code == 4
    assert lab == [("inject", "F01")]


def test_definite_rejection_reverts_and_stops(tmp_path, lab):
    def busy(request):
        raise lc.ApiError(503, "agent_busy", True)

    with pytest.raises(bench.Stop) as stop:
        make(tmp_path, FakeApi(submit=busy)).run(ROWS)
    assert stop.value.code == 2
    assert lab == [("inject", "F01"), ("revert", "F01")]
    assert results(tmp_path)[0]["status"] == "admission_error"


def test_ctrl_c_after_post_holds_lab_until_job_is_known(tmp_path, lab):
    def pending(request):
        return live_job(request, state="accepted")

    def interrupt(request):
        raise KeyboardInterrupt

    api = FakeApi(submit=pending, poll=interrupt)
    with pytest.raises(bench.Stop) as stop:
        make(tmp_path, api).run(ROWS)
    assert stop.value.code == 4
    assert lab == [("inject", "F01")]
    assert results(tmp_path) == []
    held = [e for e in bench.read_jsonl(tmp_path / "journal.jsonl") if e["event"] == "held"][0]
    assert held["job_id"] and held["request_id"]

    # Resume tanpa job terlihat: tetap ditahan, gak ada revert.
    api._poll = None
    with pytest.raises(bench.Stop) as stop:
        make(tmp_path, api).run(ROWS)
    assert stop.value.code == 4
    assert lab == [("inject", "F01")]

    # Operator sudah memastikan ke Host 1 dan melepas baris 1 secara eksplisit.
    make(tmp_path, api, release=[1]).run(ROWS)
    assert lab == [("inject", "F01"), ("revert", "F01"), ("inject", "F25"), ("revert", "F25")]


def test_ctrl_c_before_post_reverts_and_stops(tmp_path, lab, monkeypatch):
    def interrupt(fn, timeout, interval=1.0):
        raise KeyboardInterrupt

    monkeypatch.setattr(fr, "wait_for", interrupt)
    api = FakeApi()
    with pytest.raises(KeyboardInterrupt):
        make(tmp_path, api).run(ROWS)
    assert lab == [("inject", "F01"), ("revert", "F01")]
    assert api.requests == []
    assert results(tmp_path)[0]["status"] == "interrupted_operator"


def test_normal_rows_complete_in_order(tmp_path, lab):
    make(tmp_path, FakeApi()).run(ROWS)
    assert lab == [("inject", "F01"), ("revert", "F01"), ("inject", "F25"), ("revert", "F25")]
    assert [r["status"] for r in results(tmp_path)] == ["completed", "completed"]


def with_commands(commands):
    def make_job(request):
        job = live_job(request)
        job["assessment"]["commands"] = commands
        return job
    return make_job


def test_execute_applies_linted_commands_and_skips_fallback(tmp_path, lab, monkeypatch):
    monkeypatch.setattr(bench, "run_lint", lambda c: {"status": "passed", "violations": [],
                                                      "commands_sha256": lc.canonical_sha256(c)})
    fix = [{"router": "r1", "interpreter": "ip", "args": ["link", "set", "eth1", "mtu", "1500"]}]
    api = FakeApi(submit=with_commands(fix))
    make(tmp_path, api, execute=True).run(ROWS[:1])
    assert lab == [("inject", "F01"), ("exec", "r1", "ip link set eth1 mtu 1500")]
    rec = results(tmp_path)[0]
    assert rec["applied"] is True and rec["execution"]["agent_recovered"] is True
    assert rec["verification"]["source"] == "agent" and rec["fallback_revert"]["performed"] is False
    assert rec["timing"]["agent_recovery_s"] is not None


def test_rejected_lint_is_never_executed(tmp_path, lab, monkeypatch):
    monkeypatch.setattr(bench, "run_lint", lambda c: {"status": "rejected", "violations": ["x"],
                                                      "commands_sha256": lc.canonical_sha256(c)})
    fix = [{"router": "r1", "interpreter": "ip", "args": ["link", "set", "eth1", "mtu", "1500"]}]
    make(tmp_path, FakeApi(submit=with_commands(fix)), execute=True).run(ROWS[:1])
    assert lab == [("inject", "F01"), ("revert", "F01")]
    rec = results(tmp_path)[0]
    assert rec["applied"] is False and rec["fallback_revert"]["reason"] == "read_only_phase"


def test_failed_agent_command_falls_back_to_catalog_revert(tmp_path, lab, monkeypatch):
    monkeypatch.setattr(bench, "run_lint", lambda c: {"status": "passed", "violations": [],
                                                      "commands_sha256": lc.canonical_sha256(c)})
    bad = [{"router": "r1", "interpreter": "vtysh", "args": ["configure terminal", "gagal"]}]
    make(tmp_path, FakeApi(submit=with_commands(bad)), execute=True).run(ROWS[:1])
    assert lab[-1] == ("revert", "F01")
    rec = results(tmp_path)[0]
    assert rec["applied"] is True and rec["execution"]["agent_recovered"] is False
    assert rec["fallback_revert"]["reason"] == "agent_fix_failed"


def test_without_execute_flag_nothing_is_applied(tmp_path, lab, monkeypatch):
    monkeypatch.setattr(bench, "run_lint", lambda c: {"status": "passed", "violations": [],
                                                      "commands_sha256": lc.canonical_sha256(c)})
    fix = [{"router": "r1", "interpreter": "ip", "args": ["link", "set", "eth1", "mtu", "1500"]}]
    make(tmp_path, FakeApi(submit=with_commands(fix))).run(ROWS[:1])
    assert not [e for e in lab if e[0] == "exec"]
    assert results(tmp_path)[0]["applied"] is False


def test_rule_based_runs_locally_without_api(tmp_path, lab, monkeypatch):
    import gzip
    import regex_baseline as rb
    snaps = json.loads(gzip.decompress((ROOT / "data" / "rca-sim" / "regex_snapshots.json.gz").read_bytes()))
    monkeypatch.setattr(rb, "collect", lambda routers, since=None: snaps["F01"])
    monkeypatch.setattr(bench, "run_lint", lambda c: {"status": "passed", "violations": [],
                                                      "commands_sha256": lc.canonical_sha256(c)})
    api = FakeApi()
    row = [{"order": 451, "fault_id": "F01", "variant": "rule_based", "trial": 1}]
    make(tmp_path, api, execute=True).run(row)
    assert api.requests == []
    assert lab == [("inject", "F01"), ("exec", "r1", "ip link set eth1 mtu 1500")]
    rec = results(tmp_path)[0]
    assert rec["status"] == "completed" and rec["diagnosis"]["assessment"]["root_cause"] == "mtu_mismatch"
    assert rec["execution"]["agent_recovered"] is True and rec["timing"]["diagnosis_s"] is not None
