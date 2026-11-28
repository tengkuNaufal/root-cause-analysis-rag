import json

import pytest

from rca.evaluation_inputs import checked_catalog, select_attempts
from rca.evaluator import evaluate
from tests.test_evaluator_live import host2_row


def retries():
    first = host2_row(attempt=1)
    last = host2_row(attempt=2, request_id="retry-request")
    first["diagnosis"]["assessment"]["router"] = "r2"
    return [last, first]  # Deliberately not in attempt order.


def test_duplicate_cells_rejected_by_default():
    with pytest.raises(ValueError, match="Duplicate scheduled cell"):
        select_attempts(retries())


@pytest.mark.parametrize("policy,accuracy,excluded", [("first", 0.0, 2), ("last", 1.0, 1)])
def test_explicit_policy_scores_one_cell_and_keeps_audit(tmp_path, policy, accuracy, excluded):
    path = tmp_path / "runs.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in retries()))
    result = evaluate(path, tmp_path / "eval", attempt_policy=policy)
    metric = result["metrics"].iloc[0]
    assert metric["runs"] == 1 and metric["rca_accuracy"] == accuracy
    audit = json.loads((tmp_path / "eval/selection.json").read_text())
    assert audit["excluded_rows"] == 1 and audit["excluded"][0]["attempt"] == excluded
    assert len(audit["source_sha256"]) == 64


@pytest.mark.parametrize("attempt", [None, 1, 0, True])
def test_ambiguous_duplicate_attempts_rejected(attempt):
    rows = retries()
    rows[0]["attempt"] = attempt
    with pytest.raises(ValueError, match="attempt|Ambiguous"):
        select_attempts(rows, "last")


def test_order_bindings_cannot_merge_sessions():
    rows = retries()
    rows[0]["plan_order"] = 2
    with pytest.raises(ValueError, match="Multiple plan_order"):
        select_attempts(rows, "first")
    rows[0]["plan_order"] = 1
    rows[0]["trial"] = 2
    with pytest.raises(ValueError, match="Conflicting"):
        select_attempts(rows)


def test_hash_validation_includes_excluded_attempts():
    rows = retries()
    rows[0]["catalog_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="catalog_sha256"):
        checked_catalog(rows)
