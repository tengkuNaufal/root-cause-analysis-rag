"""Read current Vector state and verify FRR marker delivery without restarting services."""
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
from datetime import datetime, timezone
from log_ingestion.test_live import ROOT, run, timestamp


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    tag = 'RCA_RECOVERY_' + uuid.uuid4().hex
    expected, commands = {}, []
    result = dict(passed=False, tag=tag)
    try:
        state = json.loads(run(['docker', 'inspect', '--format', '{{json .State}}', 'rca-vector']))
        if not state['Running']:
            raise RuntimeError('Vector is not running')
        (output / 'vector-state.json').write_text(json.dumps(state, indent=2))
        for n in range(1, 7):
            router = f'r{n}'
            for daemon in (['bgpd', 'ospfd'] if n <= 4 else ['bgpd']):
                marker = f'{tag}_{router}_{daemon}'
                args = ['docker', 'exec', 'clab-rca-' + router, 'vtysh', '-d', daemon,
                        '-c', 'send log level informational ' + marker]
                commands.append(dict(command=args, stdout=run(args)))
                expected[marker] = dict(router=router, daemon='BGP' if daemon == 'bgpd' else 'OSPF')
        deadline = time.monotonic() + 30
        while True:
            found = []
            for path in sorted((ROOT / 'data/host1/logs/normalized').glob('*/*.jsonl')):
                for line_number, line in enumerate(path.read_text().splitlines(), 1):
                    if tag not in line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    found.append(dict(path=str(path.relative_to(ROOT)), line=line_number, event=event))
            if all(any(marker in row['event'].get('message', '') for row in found) for marker in expected):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Markers did not arrive within 30 seconds')
            time.sleep(.5)
        for marker, identity in expected.items():
            matches = [row for row in found if marker in row['event']['message']]
            if len(matches) != 1:
                raise RuntimeError('Missing/duplicate marker: ' + marker)
            event = matches[0]['event']
            raw = ROOT / 'data/host1/logs/raw' / identity['router'] / 'events.log'
            assert all(event[k] == v for k, v in identity.items())
            assert event['parse_status'] == 'parsed' and event['severity'] == 'informational'
            assert event['schema_version'] == 1 and event['lab'] == 'rca'
            assert event['raw_message'] in raw.read_text()
            assert timestamp(event['ingested_at']) >= timestamp(event['event_timestamp'])
        # Freeze complete source bytes so path/line citations do not depend on later appends.
        manifest = []
        paths = {ROOT / row['path'] for row in found} | {
            ROOT / 'data/host1/logs/raw' / v['router'] / 'events.log' for v in expected.values()}
        for path in sorted(paths):
            relative = path.relative_to(ROOT / 'data/host1/logs')
            dest = output / 'frozen' / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = path.read_bytes()
            dest.write_bytes(content)
            manifest.append(dict(original=str(path.relative_to(ROOT)), frozen=str(dest.relative_to(output)),
                                 sha256=hashlib.sha256(content).hexdigest()))
        (output / 'events.json').write_text(json.dumps(found, indent=2) + '\n')
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        result.update(passed=True, expected_markers=len(expected), observed_markers=len(found),
                      routers=6, bgp_markers=6, ospf_markers=4,
                      scope='Live FRR markers to Vector normalized logs; no service restart or crash-loss guarantee')
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        result['completed_at'] = datetime.now(timezone.utc).isoformat()
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1])))
