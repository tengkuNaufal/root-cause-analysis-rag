# Tes bench_status.py: ringkasan dan detail dibaca dari results.jsonl tanpa lab atau API.
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bench  # noqa: E402
import bench_status  # noqa: E402
import fault_runner as fr  # noqa: E402

EXAMPLES = json.loads((ROOT / "host1" / "live_api" / "examples.json").read_text())
FAULTS = {f["id"]: f for f in fr.load_catalog(ROOT / "faults" / "host1.yaml")}


def row(order, attempt, recovered=True, status="completed"):
    rec = bench.new_record(order, attempt, "F01", "graph_rag", 1, "sha")
    rec.update(status=status, diagnosis=copy.deepcopy(EXAMPLES["hypothesis"]), recovered=recovered, applied=True,
               lint={"status": "passed", "violations": []}, execution={"agent_recovered": recovered},
               timing={"diagnosis_s": 5.0, "agent_recovery_s": 11.0 if recovered else None})
    return rec


def write(tmp_path, rows, tail=""):
    (tmp_path / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + tail)


def test_summary_counts_latest_attempt_and_skips_partial_line(tmp_path, capsys):
    write(tmp_path, [row(1, 1, recovered=False, status="error"), row(1, 2), row(2, 1)], tail='{"plan_order": 3')
    bench_status.summary(tmp_path, FAULTS, 450)
    out = capsys.readouterr().out
    assert "2 baris selesai dari 450" in out
    assert "graph_rag     2      2       2        2     2      2" in out
    assert "perlu dicek" not in out


def test_summary_warns_about_held_row(tmp_path, capsys):
    write(tmp_path, [row(1, 1)])
    (tmp_path / "journal.jsonl").write_text(json.dumps({"event": "held", "order": 2}) + "\n")
    bench_status.summary(tmp_path, FAULTS, None)
    assert "baris 2 attempt 1 ditahan" in capsys.readouterr().out


def test_show_prints_diagnosis_and_commands(tmp_path, capsys):
    write(tmp_path, [row(7, 1)])
    bench_status.show(tmp_path, FAULTS, "last")
    out = capsys.readouterr().out
    assert "mtu_mismatch di r1" in out
    assert "r1: ip link set eth1 mtu 1500" in out
    assert "pemulihan oleh agen 11.0s" in out


def test_show_separates_diagnosis_from_api_proposal_rejection(tmp_path,capsys):
    rec=row(7,1,recovered=False)
    rec['proposal']={'status':'rejected','stage':'guard','code':'proposal_does_not_restore_observed_baseline','candidate_count':1}
    rec['diagnosis']['assessment']['commands']=[]
    write(tmp_path,[rec]);bench_status.show(tmp_path,FAULTS,'last')
    out=capsys.readouterr().out
    assert 'mtu_mismatch di r1' in out and 'Proposal ditolak API: guard' in out


def test_recovered_fallback_does_not_hide_rejected_proposal_in_summary(tmp_path,capsys):
    rec=row(7,1)
    rec['proposal']={'status':'rejected','code':'proposal_does_not_restore_observed_baseline'}
    write(tmp_path,[rec]);bench_status.summary(tmp_path,FAULTS,450)
    out=capsys.readouterr().out
    assert 'Baris yang perlu dicek' in out and 'proposal_does_not_restore_observed_baseline' in out

def test_first_held_run_is_visible_without_final_rows(tmp_path, capsys):
    (tmp_path / 'journal.jsonl').write_text(json.dumps({'event':'held','plan_order':12,'attempt':1})+'\n')
    bench_status.summary(tmp_path, FAULTS, 450)
    assert 'baris 12 attempt 1 ditahan' in capsys.readouterr().out

def test_held_retry_is_not_hidden_by_earlier_completed_attempt(tmp_path, capsys):
    write(tmp_path, [row(7,1)])
    (tmp_path / 'journal.jsonl').write_text(json.dumps({'event':'held','plan_order':7,'attempt':2})+'\n')
    bench_status.summary(tmp_path, FAULTS, 450)
    assert 'baris 7 attempt 2 ditahan' in capsys.readouterr().out

def test_fast_time_does_not_override_failed_recovery(tmp_path):
    rec=row(1,1,recovered=False)
    rec['timing']['agent_recovery_s']=2
    write(tmp_path,[rec])
    assert not bench_status.smoke(tmp_path,10)

def test_smoke_rejects_missing_faults_even_when_available_run_passes(tmp_path):
    rec=row(1,1);rec['timing']['agent_recovery_s']=2
    write(tmp_path,[rec])
    assert not bench_status.smoke(tmp_path,10,['F01','F02','F03'])
    assert bench_status.smoke(tmp_path,10,['F01'])


def test_show_prints_api_error_and_failed_command(tmp_path, capsys):
    failed = row(3, 1, recovered=False, status="job_failed")
    failed["diagnosis"] = {"state": "failed", "error": {"code": "model_timeout", "message": "deadline lewat",
                                                       "retryable": False}}
    failed["execution"] = {"agent_recovered": False, "results": [{"index": 0, "ok": False, "error": "% gagal"}]}
    write(tmp_path, [failed])
    bench_status.show(tmp_path, FAULTS, "3")
    out = capsys.readouterr().out
    assert "Error dari API: model_timeout: deadline lewat" in out
    assert "Perintah ke-0 gagal : % gagal" in out
