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
    assert "baris 2 ditahan" in capsys.readouterr().out


def test_show_prints_diagnosis_and_commands(tmp_path, capsys):
    write(tmp_path, [row(7, 1)])
    bench_status.show(tmp_path, FAULTS, "last")
    out = capsys.readouterr().out
    assert "mtu_mismatch di r1" in out
    assert "r1: ip link set eth1 mtu 1500" in out
    assert "pemulihan oleh agen 11.0s" in out
