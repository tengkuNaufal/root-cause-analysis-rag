"""Live FRR marker test and graceful Vector restart/checkpoint test; no link faults."""
import collections
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]


def timestamp(value):
    # Python 3.10 accepts microseconds; retain nanoseconds in the archived event.
    value = re.sub(r'(\.\d{6})\d+', r'\1', value)
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def run(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if p.returncode or '% Unknown' in p.stdout or "Can't open" in p.stdout:
        raise RuntimeError(f'{args}: {p.returncode}: {p.stdout} {p.stderr}')
    return p.stdout


def main():
    tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    out = ROOT / 'data/host1/log-ingestion' / tag
    out.mkdir(parents=True)
    expected = {}
    commands = []

    def emit(router, daemon, level, phase):
        marker = f'RCA_INGEST_{tag}_{phase}_{router}_{daemon}_{level}'
        args = ['docker', 'exec', 'clab-rca-' + router, 'vtysh', '-d', daemon,
                '-c', f'send log level {level} {marker}']
        stdout = run(args)
        expected[marker] = dict(router=router, daemon='BGP' if daemon == 'bgpd' else 'OSPF', severity=level)
        commands.append(dict(command=args, stdout=stdout, completed_at=datetime.now(timezone.utc).isoformat()))

    def records():
        found = []
        for path in (ROOT / 'data/host1/logs/normalized').glob('*/*.jsonl'):
            for line in path.read_text().splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # A currently appended last line may not be complete yet.
                if tag in event.get('raw_message', ''):
                    found.append(event)
        return found

    def wait_for_all():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            events = records()
            if all(any(marker in e['message'] for e in events) for marker in expected):
                return events
            time.sleep(0.5)
        raise AssertionError('Not all markers arrived within 30 seconds')

    failure = None
    try:
        for n in range(1, 7):
            for level in ('informational', 'warnings'):
                emit(f'r{n}', 'bgpd', level, 'live')
            if n <= 4:
                emit(f'r{n}', 'ospfd', 'informational', 'live')
        first = wait_for_all()
        run(['docker', 'stop', '--time', '15', 'rca-vector'])
        try:
            for n in range(1, 7):
                emit(f'r{n}', 'bgpd', 'informational', 'while_vector_stopped')
        finally:
            run(['docker', 'start', 'rca-vector'])
        events = wait_for_all()
        time.sleep(2)  # Allow the persisted read checkpoint to reveal any replay duplicates.
        events = records()
        for marker, wanted in expected.items():
            matches = [e for e in events if marker in e['message']]
            assert len(matches) == 1, (marker, len(matches))
            event = matches[0]
            assert all(event[k] == v for k, v in wanted.items()), (marker, event)
            assert event['parse_status'] == 'parsed' and event['schema_version'] == 1
            assert event['source_file'] == f'/frr/{wanted["router"]}/events.log'
            raw = (ROOT / f'data/host1/logs/raw/{wanted["router"]}/events.log').read_text()
            assert event['raw_message'] in raw
            assert timestamp(event['ingested_at']) >= timestamp(event['event_timestamp'])
        result = dict(passed=True, expected_markers=len(expected), observed_markers=len(events),
                      first_phase=len(first), recovered_after_stop=6,
                      per_router=dict(collections.Counter(e['router'] for e in events)),
                      scope='Real FRR send log markers; graceful Vector restart; no routing fault or crash-loss test')
    except Exception as exc:
        failure = exc
        result = dict(passed=False, error=str(exc))
    finally:
        (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        (out / 'expected.json').write_text(json.dumps(expected, indent=2) + '\n')
        shutil.copytree(ROOT / 'data/host1/logs/raw', out / 'raw')
        shutil.copytree(ROOT / 'data/host1/logs/normalized', out / 'normalized')
        hashes = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for folder in ('raw', 'normalized') for p in (out / folder).rglob('*') if p.is_file()}
        (out / 'evidence-sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
        print(json.dumps({'output': str(out), **result}, indent=2), flush=True)
    if failure:
        raise failure


if __name__ == '__main__':
    main()
