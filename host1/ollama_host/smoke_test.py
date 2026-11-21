"""Standalone inference checks; never reads live network data or executes model text."""
import json
from pathlib import Path
import time
import urllib.request
import argparse

BASE = 'http://127.0.0.1:11434'
MODEL = 'llama3.1:8b'

def request(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.load(response)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    profile = json.loads((Path(__file__).with_name('inference-profile.json')).read_text())
    parser.add_argument('--num-gpu', type=int, default=profile['options']['num_gpu'],
                        help='Offload layer count; defaults to the verified project profile')
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    (output / 'version.json').write_text(json.dumps(request('/api/version'), indent=2))
    tags = request('/api/tags')
    (output / 'tags.json').write_text(json.dumps(tags, indent=2))
    model_tag = next(item for item in tags['models'] if item['name'] == MODEL)
    assert model_tag['digest'] == profile['expected_digest'], 'Model digest differs from verified profile'
    show = request('/api/show', {'model': MODEL})
    (output / 'model-show.json').write_text(json.dumps(show, indent=2))
    assert show['details']['parameter_size'] == '8.0B'
    assert show['details']['quantization_level'] == 'Q4_K_M'
    schema = {'type': 'object', 'properties': {'status': {'type': 'string', 'enum': ['ok']},
              'execution_allowed': {'type': 'boolean', 'const': False}},
              'required': ['status', 'execution_allowed'], 'additionalProperties': False}
    checks = []
    for name in ('cold', 'warm'):
        body = {'model': MODEL, 'stream': False, 'keep_alive': '5m', 'format': schema,
                'prompt': 'Return a JSON object with status ok and execution_allowed false. No other fields.',
                'options': dict(profile['options'])}
        if args.num_gpu is not None:
            body['options']['num_gpu'] = args.num_gpu
        (output / f'{name}-request.json').write_text(json.dumps(body, indent=2))
        start = time.monotonic()
        result = request('/api/generate', body)
        elapsed = time.monotonic() - start
        (output / f'{name}-response.json').write_text(json.dumps(result, indent=2))
        parsed = json.loads(result['response'])
        assert result['done'] and result.get('done_reason') == 'stop', result
        assert isinstance(parsed, dict) and set(parsed) == {'status', 'execution_allowed'}, parsed
        assert parsed['status'] == 'ok' and parsed['execution_allowed'] is False, parsed
        count, duration = result.get('eval_count', 0), result.get('eval_duration', 0)
        checks.append(dict(name=name, passed=True, wall_seconds=elapsed,
                           load_seconds=result.get('load_duration', 0) / 1e9,
                           generated_tokens=count,
                           tokens_per_second=count / (duration / 1e9) if duration else None))
        (output / f'{name}-ps.json').write_text(json.dumps(request('/api/ps'), indent=2))
    summary = dict(passed=True, model=MODEL, num_ctx=2048, num_gpu=args.num_gpu, trials=checks,
                   scope='Standalone synthetic JSON inference only; no RCA, agent integration or remediation')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
