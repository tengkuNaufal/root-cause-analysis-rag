# Tes pembanding regex pakai teks yang direkam dari lab tiruan rca (data/rca-sim/regex_snapshots.json.gz):
# satu snapshot per fault saat gejala pertama terdeteksi, plus satu snapshot lab normal.
import gzip
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fault_runner as fr  # noqa: E402
import live_client as lc  # noqa: E402
import regex_baseline as rb  # noqa: E402

SNAPSHOTS = json.loads(gzip.decompress((ROOT / "data" / "rca-sim" / "regex_snapshots.json.gz").read_bytes()))
FAULTS = {f["id"]: f for f in fr.load_catalog(ROOT / "faults" / "host1.yaml")}


@pytest.mark.parametrize("fault_id", sorted(FAULTS))
def test_rules_find_class_and_router(fault_id):
    found = rb.diagnose(SNAPSHOTS[fault_id])
    fault = FAULTS[fault_id]
    assert found is not None
    assert (found.cls, found.router) == (fault["class"], fault["ground_truth"]["router"])
    assert found.evidence


@pytest.mark.parametrize("fault_id", sorted(FAULTS))
def test_rule_commands_pass_linter(fault_id):
    sys.path.insert(0, str(ROOT))
    from rca import linter
    found = rb.diagnose(SNAPSHOTS[fault_id])
    assert linter.lint(found.commands)["passed"]


def test_healthy_lab_abstains():
    assert rb.diagnose(SNAPSHOTS["baseline"]) is None


def test_job_has_live_shape_and_citable_evidence():
    request = lc.new_request(rb.VARIANT, lc.utc_now())
    job = rb.make_job(request, SNAPSHOTS["F19"])
    assert job["state"] == "completed" and job["variant"] == "rule_based" and job["simulation"] is False
    a = job["assessment"]
    assert (a["root_cause"], a["router"]) == ("bgp_wrong_remote_as", "r2")
    assert set(a["evidence_ids"]) == {e["id"] for e in job["evidence"]}
    assert job["result"]["root_cause_class"] == a["root_cause"]

    empty = rb.make_job(request, SNAPSHOTS["baseline"])
    assert empty["result"]["status"] == "abstain" and empty["assessment"]["commands"] == []


def test_recent_log_drops_lines_before_inject():
    text = "2026/11/28 05:00:00.1 old\n2026/11/28 05:10:00.5 new"
    assert rb.recent_log(text, "2026-11-28T05:05:00Z") == "2026/11/28 05:10:00.5 new"


def test_plan_appends_rule_based_after_agent_rows():
    rows = (ROOT / "data" / "benchmark_plan.csv").read_text().splitlines()[1:]
    variants = [r.split(",")[2] for r in rows]
    assert len(rows) == 600
    assert set(variants[:450]) == {"zero_shot", "text_rag", "graph_rag"}
    assert set(variants[450:]) == {"rule_based"}
