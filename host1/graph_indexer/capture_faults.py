"""Authorized Host 1 L12/L35 tests with frozen Vector evidence after restoration."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

from telemetry.collector import ROOT, write_json
from telemetry.test_link_faults import main as fault_test, command


def main():
    run = ROOT / 'data/host1/integration-faults' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    code = fault_test(run)  # Each link restored in finally; baseline verified after each case.
    if code:
        raise RuntimeError('Fault baseline verification failed')
    # Flush barriers are not fault evidence: they only confirm Vector has read each file.
    markers = []
    for n in range(1, 7):
        marker = f'RCA_CORRELATION_DRAIN_{run.name}_r{n}'
        result = command(f'r{n}', 'vtysh', '-d', 'bgpd', '-c', f'send log level informational {marker}')
        if '%' in result:
            raise RuntimeError(result)
        markers.append(marker)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        files = {p: p.read_bytes() for p in (ROOT / 'data/host1/logs/normalized').glob('*/*.jsonl')}
        text = b'\n'.join(files.values()).decode()
        if all(marker in text for marker in markers):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError('Vector drain timeout; links already restored')
    frozen = []
    for path, data in files.items():
        complete = data[:data.rfind(b'\n') + 1]
        target = run / 'logs' / path.relative_to(ROOT / 'data/host1/logs/normalized')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(complete)
        frozen.append(dict(path=str(target.relative_to(run)), partial_tail_bytes=len(data) - len(complete)))
    shutil.copytree(ROOT / 'data/host1/logs/raw', run / 'frr-raw')
    write_json(run / 'capture.json', dict(completed_at=datetime.now(timezone.utc).isoformat(),
        drain_markers=markers, files=frozen, note='Drain markers are transport checks, not evidence of routing faults'))
    print(json.dumps({'capture_complete': str(run)}), flush=True)


if __name__ == '__main__':
    main()
