import json

import pytest

from rca.evaluator import evaluate, score_run, wilson


def _run(fault_id="F01", variant="text_rag", router="r1", cls="mtu_mismatch", recovered=True, **kw):
    run = {
        "run_id": f"{fault_id}-{variant}-1", "fault_id": fault_id, "variant": variant, "trial": 1,
        "agent": {"router": router, "root_cause": cls, "confidence": 0.9, "evidence_ids": ["e1", "e2"],
                  "commands": [{"router": "r1", "commands": ["ip link set dev eth1 mtu 1500"]}],
                  "explanation": "MTU eth1 r1 1400 vs 1500 di r2"},
        "evidence_ids_available": ["e1", "e2", "e3"],
        "lint": {"passed": True, "violations": []},
        "applied": True, "recovered": recovered, "t_diagnosis_s": 3.0, "t_recovery_s": 6.0 if recovered else None,
    }
    run.update(kw)
    return run


def test_correct_run(catalog, linter):
    s = score_run(_run(), catalog, linter)
    assert s["rca_ok"] and s["cmd_ok"] and not s["halluc"]


def test_wrong_router_is_not_rca_ok(catalog, linter):
    s = score_run(_run(router="r2"), catalog, linter)
    assert s["class_ok"] and not s["router_ok"] and not s["rca_ok"]


def test_hallucinated_evidence_and_interface(catalog, linter):
    run = _run()
    run["agent"]["evidence_ids"].append("e-tidak-ada")
    assert score_run(run, catalog, linter)["halluc_evidence"]
    run = _run()
    run["agent"]["commands"] = [{"router": "r5", "commands": ["ip link set dev eth3 mtu 1500"]}]
    s = score_run(run, catalog, linter)
    assert s["halluc_command"] and not s["halluc_evidence"]


def test_lint_recomputed_when_missing(catalog, linter):
    run = _run()
    del run["lint"]
    run["agent"]["commands"] = [{"router": "r1", "commands": ["reload"]}]
    s = score_run(run, catalog, linter)
    assert not s["lint_passed"] and not s["cmd_ok"]


def test_alias_fields_accepted(catalog, linter):
    run = {"fault_id": "F13", "variant": "graph_rag", "trial": 2,
           "answer": {"router": "r1", "root_cause": "ospf_auth_mismatch", "commands": []},
           "applied": True, "verification": {"passed": True}, "timing": {"diagnosis_s": 2.0, "recovery_s": 5.0}}
    s = score_run(run, catalog, linter)
    assert s["rca_ok"] and s["recovered"] and s["t_diagnosis_s"] == 2.0 and s["t_recovery_s"] == 5.0


def test_wilson_interval():
    lo, hi = wilson(8, 10)
    assert 0.44 < lo < 0.5 and 0.94 < hi < 0.97


def test_end_to_end(tmp_path):
    runs = [_run(variant=v, t_diagnosis_s=t) for v, t in [("zero_shot", 1), ("zero_shot", 3), ("graph_rag", 5)]]
    runs.append(_run(variant="graph_rag", router="r9", recovered=False))
    p = tmp_path / "runs.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in runs), encoding="utf-8")
    res = evaluate(p, tmp_path / "out")
    m = res["metrics"].set_index("variant")
    assert list(m.index) == ["zero_shot", "graph_rag"]
    assert m.loc["zero_shot", "rca_accuracy"] == 1.0
    assert m.loc["zero_shot", "t_diag_median_s"] == pytest.approx(2.0)
    assert m.loc["graph_rag", "rca_accuracy"] == 0.5
    for f in ("report.md", "metrics_by_variant.csv", "accuracy_by_class.csv", "boxplot_diagnosis_time.png",
              "boxplot_recovery_time.png"):
        assert (tmp_path / "out" / f).exists()


def test_agent_contract_response(catalog, linter):
    """Respons host1/agent_contract: commands dari proposed_patch, evidence dari claims + patch."""
    run = {"fault_id": "F01", "variant": "text_rag", "trial": 1, "recovered": True, "applied": True,
           "evidence_ids_available": ["e1", "e2"],
           "agent": {"status": "hypothesis", "root_cause_hypothesis": "MTU r1 eth1 1400",
                     "root_cause_class": "mtu_mismatch",
                     "claims": [{"statement": "OSPF r1-r2 ExStart", "evidence_ids": ["e1"]}],
                     "proposed_patch": [{"router": "r1", "interpreter": "linux_argv",
                                         "arguments": ["ip", "link", "set", "eth1", "mtu", "1500"],
                                         "evidence_ids": ["e9"], "rationale": "x"}]}}
    s = score_run(run, catalog, linter)
    assert s["rca_ok"] and s["lint_passed"] and s["cmd_ok"]
    assert s["halluc_evidence"]  # e9 tidak pernah dikirim ke agen
    assert "ExStart" in s["explanation"]
