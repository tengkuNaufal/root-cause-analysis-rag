import copy
import csv
import hashlib
import json

import pytest

from rca.explain import aggregate, main, sample
from rca.rubric_evidence import bundle, canonical
from tests.test_evaluator_live import host2_row


def write_runs(tmp_path, rows):
    path = tmp_path / "runs.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def archived(tmp_path, *, locator="/observations/0"):
    row = host2_row(attempt=1)
    diag = row["diagnosis"]
    row.update(request_id=diag["request_id"], job_id=diag["job_id"])
    diag["provenance"]["model_evidence_ids"] = ["e1"]
    archive = tmp_path / "archive"
    jobdir = archive / diag["job_id"]
    jobdir.mkdir(parents=True)
    observation = {"router": "r1", "interface": "eth1", "mtu": 1400}
    source = {"observations": [observation]}
    raw = json.dumps(source).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (jobdir / "facts.json").write_bytes(raw)
    manifest = diag["evidence"][0]
    manifest.update(source_sha256=sha, source_id="sha256:" + sha, locator=locator)
    fragment = source if locator == "/" else observation
    payload = {k: manifest[k] for k in ("id", "kind", "source_id", "source_sha256", "locator")}
    payload["content"] = canonical(fragment)
    index = [{"payload": payload, "file": "facts.json", "manifest": manifest}]
    (jobdir / "evidence-index.json").write_text(json.dumps(index))
    return row, archive, jobdir


def read_csv(path):
    with path.open(encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def test_packet_contains_verified_anonymous_evidence_and_reproducible_key(tmp_path):
    row, archive, _ = archived(tmp_path)
    path = write_runs(tmp_path, [row])
    out = tmp_path / "rubric"
    sample(path, out, ["a", "b", "c"], 42, 9, evidence_root=archive)
    rating = read_csv(out / "penilaian_a.csv")[0]
    key = read_csv(out / "kunci_sampel.csv")[0]
    packet = out / rating["evidence_bundle"]
    evidence = json.loads(packet.read_text())["evidence"][0]
    assert json.loads(evidence["content"])["mtu"] == 1400
    assert set(evidence) == {"id", "kind", "content"}
    assert not {"variant", "request_id", "job_id", "plan_order", "attempt"} & set(rating)
    assert row["job_id"] not in packet.read_text() and row["variant"] not in packet.read_text()
    assert key["run_id"] == key["request_id"] == row["request_id"]
    assert key["job_id"] == row["job_id"] and key["attempt"] == "1" and key["plan_order"] == "1"
    assert key["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert key["bundle_sha256"] == hashlib.sha256(packet.read_bytes()).hexdigest()
    assert key["row_sha256"] == hashlib.sha256(canonical(row).encode()).hexdigest()
    assert json.loads(key["evidence_hashes"])[0]["source_sha256"] == row["diagnosis"]["evidence"][0]["source_sha256"]
    assert json.loads((out / "selection.json").read_text())["overlap"] == 1


@pytest.mark.parametrize("damage", ["bytes", "fragment", "binding", "escape", "duplicate"])
def test_corrupt_evidence_rejected_before_any_packet_is_written(tmp_path, damage):
    row, archive, jobdir = archived(tmp_path)
    index_path = jobdir / "evidence-index.json"
    index = json.loads(index_path.read_text())
    if damage == "bytes":
        (jobdir / "facts.json").write_text("{}")
    elif damage == "fragment":
        index[0]["payload"]["content"] = "invented observation"
    elif damage == "binding":
        index[0]["payload"]["source_id"] = "sha256:" + "0" * 64
    elif damage == "escape":
        index[0]["file"] = "../../outside.json"
    else:
        index.append(copy.deepcopy(index[0]))
    index_path.write_text(json.dumps(index))
    out = tmp_path / "rubric"
    with pytest.raises(ValueError):
        sample(write_runs(tmp_path, [row]), out, ["a"], 42, 0, evidence_root=archive)
    assert not out.exists()


def test_missing_archive_fails_closed(tmp_path):
    path = write_runs(tmp_path, [host2_row()])
    with pytest.raises(ValueError, match="evidence-root"):
        sample(path, tmp_path / "out", ["a"], 42, 0)
    assert not (tmp_path / "out").exists()


def test_catalog_hash_mismatch_rejected_even_for_excluded_variant(tmp_path):
    row = host2_row(variant="rule_based", catalog_sha256="0" * 64)
    with pytest.raises(ValueError, match="catalog_sha256"):
        sample(write_runs(tmp_path, [row]), tmp_path / "out", ["a"], 42, 0)
    assert not (tmp_path / "out").exists()


def test_explicit_catalog_and_environment_override_use_same_validation(tmp_path, monkeypatch):
    from rca.catalog import SAMPLE_CATALOG
    row = host2_row("abstain", catalog_sha256=hashlib.sha256(SAMPLE_CATALOG.read_bytes()).hexdigest())
    path = write_runs(tmp_path, [row])
    monkeypatch.setenv("RCA_CATALOG", str(SAMPLE_CATALOG))
    sample(path, tmp_path / "env", ["a"], 42, 0)
    monkeypatch.delenv("RCA_CATALOG")
    sample(path, tmp_path / "explicit", ["a"], 42, 0, catalog_path=SAMPLE_CATALOG)
    assert read_csv(tmp_path / "env/kunci_sampel.csv") == read_csv(tmp_path / "explicit/kunci_sampel.csv")


def test_retry_policy_shared_with_numeric_evaluator(tmp_path):
    row, archive, _ = archived(tmp_path)
    retry = copy.deepcopy(row)
    retry.update(attempt=2, request_id="retry-request")
    path = write_runs(tmp_path, [retry, row])
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="Duplicate scheduled cell"):
        sample(path, out, ["a"], 42, 0, evidence_root=archive)
    sample(path, out, ["a"], 42, 0, evidence_root=archive, attempt_policy="first")
    key = read_csv(out / "kunci_sampel.csv")[0]
    assert key["attempt"] == "1"
    assert json.loads((out / "selection.json").read_text())["excluded_rows"] == 1


def test_empty_failed_or_abstain_predictions_need_no_archive(tmp_path):
    rows = [host2_row("abstain"), host2_row("failed", variant="text_rag", plan_order=2)]
    out = tmp_path / "out"
    sample(write_runs(tmp_path, rows), out, ["a"], 42, 0)
    assert len(read_csv(out / "penilaian_a.csv")) == 2
    assert all(json.loads(p.read_text())["evidence"] == [] for p in (out / "evidence").glob("*.json"))


def test_variants_are_explicit_and_default_matches_ninety_item_rubric(tmp_path):
    rows = [host2_row("abstain", variant=v, plan_order=i + 1)
            for i, v in enumerate(["zero_shot", "text_rag", "graph_rag", "rule_based"])]
    path = write_runs(tmp_path, rows)
    sample(path, tmp_path / "agents", ["a"], 42, 0)
    assert len(read_csv(tmp_path / "agents/kunci_sampel.csv")) == 3
    assert main(["sample", str(path), "--out", str(tmp_path / "all"), "--raters", "a", "--overlap", "0",
                 "--variants", "zero_shot", "text_rag", "graph_rag", "rule_based"]) == 0
    assert len(read_csv(tmp_path / "all/kunci_sampel.csv")) == 4


def test_local_rule_excerpts_are_bound_to_input_and_packaged_offline(tmp_path):
    row = host2_row(variant="rule_based")
    row["diagnosis"].update(mode="local", variant="rule_based", evidence=[
        {"id": "e1", "kind": "cli_output", "source_id": "r1:interface", "locator": "line:0", "excerpt": "eth1 mtu 1400"}])
    row["diagnosis"]["provenance"].pop("model_evidence_ids")
    out = tmp_path / "out"
    sample(write_runs(tmp_path, [row]), out, ["a"], 42, 0, variants=["rule_based"])
    fragment = json.loads((out / "evidence/X001.json").read_text())["evidence"][0]
    assert fragment["content"] == "eth1 mtu 1400"
    key = read_csv(out / "kunci_sampel.csv")[0]
    assert json.loads(key["evidence_hashes"])[0]["source_sha256"] is None


def test_unknown_fault_and_existing_rating_output_rejected(tmp_path):
    path = write_runs(tmp_path, [host2_row("abstain", fault_id="unknown")])
    with pytest.raises(ValueError, match="Unknown catalog fault"):
        sample(path, tmp_path / "out", ["a"], 42, 0)
    out = tmp_path / "already-rated"
    out.mkdir()
    (out / "penilaian_a.csv").write_text("operator ratings")
    with pytest.raises(FileExistsError):
        sample(path, out, ["a"], 42, 0)
    assert (out / "penilaian_a.csv").read_text() == "operator ratings"


def test_packet_still_aggregates_after_human_scoring(tmp_path):
    path = write_runs(tmp_path, [host2_row("abstain")])
    out = tmp_path / "out"
    sample(path, out, ["a"], 42, 1)
    ratings = read_csv(out / "penilaian_a.csv")
    for dim in ("grounding", "kausal", "konsistensi", "perbaikan", "kejelasan"):
        ratings[0][dim] = "0"
    with (out / "penilaian_a.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ratings[0]))
        writer.writeheader()
        writer.writerows(ratings)
    aggregate(out)
    summary = read_csv(out / "ringkasan.csv")
    assert summary[0]["n"] == "1" and float(summary[0]["total"]) == 0


def test_whole_source_root_locator_supported(tmp_path):
    row, archive, _ = archived(tmp_path, locator="/")
    fragments, _ = bundle(row, ["e1"], archive)
    assert "observations" in json.loads(fragments[0]["content"])
