"""Verify the local manifest and every referenced model blob against its digest."""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

root = Path(__file__).resolve().parents[2]
run = root / sys.argv[1]
events = [json.loads(line) for line in (run / 'pull.jsonl').read_text().splitlines() if line.strip()]
assert events and events[-1].get('status') == 'success', events[-1:]
assert not any('error' in event for event in events), 'Pull reported error'
store = root / 'private/runtime/ollama/models'
manifest = store / 'manifests/registry.ollama.ai/library/llama3.1/8b'
content = manifest.read_bytes()
manifest_digest = hashlib.sha256(content).hexdigest()
with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=15) as response:
    tags = json.load(response)
(run / 'tags-after.json').write_text(json.dumps(tags, indent=2))
model = next(m for m in tags['models'] if m['name'] == 'llama3.1:8b')
payload = json.loads(content)
# Recent Ollama stores a local wrapper containing the original registry manifest
# as a separate content-addressed layer. Verify both representations explicitly.
if model['digest'] != manifest_digest:
    original_layers = [layer for layer in payload['layers']
                       if layer['mediaType'] == 'application/vnd.docker.distribution.manifest.v2+json'
                       and layer['digest'] == 'sha256:' + model['digest']]
    assert len(original_layers) == 1, 'API digest missing from wrapper manifest'
    original_path = store / 'blobs' / ('sha256-' + model['digest'])
    original_content = original_path.read_bytes()
    assert hashlib.sha256(original_content).hexdigest() == model['digest']
    original = json.loads(original_content)
    assert original['config'] == payload['config']
    assert original['layers'] == [layer for layer in payload['layers'] if layer not in original_layers]
checks = []
for blob in [payload['config'], *payload['layers']]:
    algorithm, expected = blob['digest'].split(':')
    assert algorithm == 'sha256' and len(expected) == 64
    path = store / 'blobs' / ('sha256-' + expected)
    assert path.stat().st_size == blob['size']
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
            digest.update(block)
    assert digest.hexdigest() == expected, 'Blob mismatch: ' + str(path)
    checks.append(dict(digest=blob['digest'], size=blob['size'], passed=True))
report = dict(passed=True, model=model['name'], digest=model['digest'],
              stored_manifest_sha256=manifest_digest,
              details=model['details'], total_size=model['size'], blobs=checks)
(run / 'model-verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
