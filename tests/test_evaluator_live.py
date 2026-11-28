"""Evaluator pada baris JSONL Host 2 sesuai docs/host1/LIVE-API-DRAFT.md ("Catatan JSONL milik Host 2").

Respons diagnosis diambil dari contoh resmi host1/live_api/examples.json (F01, r1, mtu_mismatch).
"""
import copy
import hashlib
import json
import math
from pathlib import Path

import pytest

from rca.evaluator import evaluate, score_run

EXAMPLES = Path(__file__).resolve().parents[1] / "host1" / "live_api" / "examples.json"
pytestmark = pytest.mark.skipif(not EXAMPLES.exists(), reason="host1/live_api/examples.json belum ada")
EX = json.loads(EXAMPLES.read_text(encoding="utf-8")) if EXAMPLES.exists() else {}


def host2_row(diagnosis="hypothesis", **kw):
    """Baris read-only: tidak ada eksekusi, jaringan dipulihkan fallback revert katalog."""
    row = {
        "plan_order": 1, "fault_id": "F01", "variant": "graph_rag", "trial": 1,
        "catalog_sha256": hashlib.sha256((EXAMPLES.parents[2] / "faults" / "host1.yaml").read_bytes()).hexdigest(), "request_id": "req-1", "job_id": "job-1",
        "timing": {"t_inject": 0.0, "t_symptom": 12.5, "t_request": 12.7, "t_diagnosis_done": 18.0,
                   "t_lint_done": 18.2, "t_apply_done": None, "t_verified": 30.0},
        "symptoms": [],
        "diagnosis": copy.deepcopy(EX[diagnosis]),
        "lint": copy.deepcopy(EX["lint_output"]),
        "execution": None,
        "verification": {"passed": True},
        "fallback_revert": {"performed": True, "reason": "read_only"},
        "recovered": True, "error": None, "status": "completed", "completion_unknown": False,
    }
    row.update(kw)
    return row


def test_assessment_is_read(catalog, linter):
    s = score_run(host2_row(), catalog, linter)
    assert (s["pred_router"], s["pred_class"]) == ("r1", "mtu_mismatch")
    assert s["rca_ok"] and s["lint_passed"] and not s["incomplete_prediction"]
    assert not s["halluc"]  # e1 ada di manifest evidence contoh


def test_timing_from_runner_points(catalog, linter):
    s = score_run(host2_row(), catalog, linter)
    assert s["t_diagnosis_s"] == pytest.approx(5.5)  # t_diagnosis_done - t_symptom
    assert s["t_recovery_s"] is None  # dipulihkan revert, bukan agen


@pytest.mark.parametrize("timing", [
    {"t_symptom": {"utc": "2026-11-21T00:00:10Z", "elapsed_s": 10.0},
     "t_diagnosis_done": {"utc": "2026-11-21T00:00:14Z", "elapsed_s": 14.0}},
    {"t_symptom_elapsed_s": 10.0, "t_diagnosis_done_elapsed_s": 14.0},
    {"t_symptom": "2026-11-21T00:00:10Z", "t_diagnosis_done": "2026-11-21T00:00:14Z"},
    {"t_symptom_utc": "2026-11-21T00:00:10+00:00", "t_diagnosis_done_utc": "2026-11-21T00:00:14+00:00"},
])
def test_timing_formats(catalog, linter, timing):
    assert score_run(host2_row(timing=timing), catalog, linter)["t_diagnosis_s"] == pytest.approx(4.0)


def test_read_only_revert_is_not_agent_success(catalog, linter):
    s = score_run(host2_row(), catalog, linter)
    assert not s["applied"] and s["recovered"] and s["fallback_revert"]
    assert not s["agent_recovered"] and not s["cmd_ok"]


def test_applied_defaults_to_false(catalog, linter):
    row = host2_row()
    del row["execution"]
    row.pop("fallback_revert")
    assert not score_run(row, catalog, linter)["applied"]


def test_applied_execution_recovers(catalog, linter):
    row = host2_row(execution={"applied": True}, fallback_revert={"performed": False})
    s = score_run(row, catalog, linter)
    assert s["applied"] and s["agent_recovered"] and s["cmd_ok"]
    assert s["t_recovery_s"] == pytest.approx(17.5)  # t_verified - t_symptom


def test_lint_rejected_status(catalog, linter):
    lint = {**EX["lint_output"], "status": "rejected", "violations": [{"command_index": 0, "code": "x"}]}
    assert not score_run(host2_row(lint=lint), catalog, linter)["lint_passed"]


def test_hallucinated_evidence_against_manifest(catalog, linter):
    row = host2_row()
    row["diagnosis"]["assessment"]["evidence_ids"].append("e-tidak-ada")
    assert score_run(row, catalog, linter)["halluc_evidence"]


def test_abstain_is_incomplete_not_error(catalog, linter):
    s = score_run(host2_row("abstain"), catalog, linter)
    assert s["abstain"] and s["incomplete_prediction"] and not s["rca_ok"] and not s["agent_error"]


@pytest.mark.parametrize("name", ["failed", "interrupted"])
def test_failed_jobs_are_errors(catalog, linter, name):
    s = score_run(host2_row(name), catalog, linter)
    assert s["agent_error"] and not s["rca_ok"]


def test_simulation_flagged_and_end_to_end(tmp_path):
    rows = [host2_row(), host2_row("abstain", fault_id="F04", variant="zero_shot", plan_order=2)]
    p = tmp_path / "pilot.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    res = evaluate(p, tmp_path / "out")
    m = res["metrics"].set_index("variant")
    assert m.loc["graph_rag", "rca_accuracy"] == 1.0
    assert math.isnan(m.loc["graph_rag", "fix_success_rate"])  # belum ada eksekusi
    assert m.loc["graph_rag", "fallback_revert_rate"] == 1.0
    assert m.loc["zero_shot", "abstain_rate"] == 1.0
    assert "data sintetis" in (tmp_path / "out" / "report.md").read_text(encoding="utf-8")


def test_catalog_hash_mismatch_rejected(tmp_path):
    row = host2_row(catalog_sha256="0" * 64)
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="catalog_sha256"):
        evaluate(path, tmp_path / "out")


def test_partial_execution_error_is_not_agent_success(catalog, linter):
    row = host2_row(applied=True, execution={"status": "execution_error", "error": "partial failure"},
                    fallback_revert={"performed": False})
    scored = score_run(row, catalog, linter)
    assert not scored["agent_recovered"] and not scored["cmd_ok"]
