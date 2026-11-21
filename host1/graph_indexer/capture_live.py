"""Capture Host 1 snapshots around FRR log markers, then freeze Vector evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import uuid

from telemetry.collector import ROOT, collect_snapshot, load_plan, write_json


def main():
    tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    out = ROOT / 'data/host1/integration' / tag
    out.mkdir(parents=True)
    plan = load_plan(ROOT / 'lab/host1/frr/design-plan.json')
    write_json(out / 'inventory.json', plan)
    expected = []
    before = collect_snapshot(plan, out / 'before')
    assert before['status'] == 'complete'
    for n in range(1, 7):
        for daemon in (['bgpd', 'ospfd'] if n <= 4 else ['bgpd']):
            marker = f'RCA_CORRELATE_{tag}_r{n}_{daemon}'
            command = ['docker', 'exec', f'clab-rca-r{n}', 'vtysh', '-d', daemon,
                       '-c', f'send log level informational {marker}']
            p = subprocess.run(command, capture_output=True, text=True, timeout=15)
            assert p.returncode == 0 and '%' not in p.stdout, (command, p.stdout, p.stderr)
            expected.append(dict(router=f'r{n}', daemon='BGP' if daemon == 'bgpd' else 'OSPF', marker=marker,
                                 command=command, stdout=p.stdout, stderr=p.stderr))
    after = collect_snapshot(plan, out / 'after')
    assert after['status'] == 'complete'
    write_json(out / 'expected.json', expected)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        captures = {p: p.read_bytes() for p in (ROOT / 'data/host1/logs/normalized').glob('*/*.jsonl')}
        text = b'\n'.join(captures.values()).decode()
        if all(e['marker'] in text for e in expected):
            break
        time.sleep(0.5)
    else:
        raise AssertionError('Vector did not deliver all markers')
    frozen = out / 'logs'
    details = []
    for path, content in captures.items():
        complete = content[:content.rfind(b'\n') + 1]
        target = frozen / path.relative_to(ROOT / 'data/host1/logs/normalized')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(complete)
        details.append(dict(source=str(path), frozen=str(target), complete_bytes=len(complete),
                            partial_tail_bytes=len(content) - len(complete)))
    write_json(out / 'capture.json', dict(tag=tag, completed_at=datetime.now(timezone.utc).isoformat(),
               expected_markers=len(expected), files=details, snapshot_counts=[before['source_counts'], after['source_counts']]))
    print(str(out), flush=True)


if __name__ == '__main__':
    main()
