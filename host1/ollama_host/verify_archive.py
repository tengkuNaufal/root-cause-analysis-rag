"""Verify pinned upstream asset digest before extracting project-local binaries."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import shutil

root = Path(__file__).resolve().parents[2]
run = root / sys.argv[1]
release = json.loads((run / 'release.json').read_text())
asset = next(a for a in release['assets'] if a['name'] == 'ollama-linux-amd64.tar.zst')
archive = root / 'private/runtime/ollama' / f"ollama-linux-amd64-{release['tag_name']}.tar.zst"
digest = hashlib.sha256()
with archive.open('rb') as source:
    for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
        digest.update(block)
assert archive.stat().st_size == asset['size'], 'Archive size mismatch'
assert 'sha256:' + digest.hexdigest() == asset['digest'], 'Upstream digest mismatch'
(run / 'archive-verification.json').write_text(json.dumps(dict(
    version=release['tag_name'], url=asset['browser_download_url'],
    size=archive.stat().st_size, sha256=digest.hexdigest(), passed=True), indent=2))
sys.path.insert(0, str(root / 'private/runtime/ollama/python-deps'))
import zstandard
destination = root / 'private/runtime/ollama/dist'
destination.mkdir(exist_ok=False)
with archive.open('rb') as source, zstandard.ZstdDecompressor().stream_reader(source) as reader:
    process = subprocess.Popen(['tar', '-x', '-f', '-', '-C', str(destination)], stdin=subprocess.PIPE)
    try:
        shutil.copyfileobj(reader, process.stdin)
    finally:
        process.stdin.close()
    assert process.wait() == 0, 'Extraction failed'
print('Verified archive and extracted:', destination)
