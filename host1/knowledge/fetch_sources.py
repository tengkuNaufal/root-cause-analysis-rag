"""Freeze official FRR/OpenConfig source documentation with immutable Git revisions."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'host1/knowledge'


def get(url):
    with urlopen(Request(url, headers={'User-Agent': 'Host1-Knowledge-Retriever'}), timeout=60) as response:
        return response.read()


def main():
    target = BASE / 'sources'
    target.mkdir(exist_ok=False)
    sources = []
    for repo, ref, platform, paths in [
        ('FRRouting/frr', 'frr-10.7.1', 'frr', ['doc/user/ospfd.rst', 'doc/user/bgp.rst', 'doc/user/zebra.rst']),
        ('openconfig/public', 'master', 'openconfig', ['release/models/interfaces/openconfig-interfaces.yang',
            'release/models/bgp/openconfig-bgp-common.yang', 'release/models/bgp/openconfig-bgp-neighbor.yang'])]:
        commit = json.loads(get(f'https://api.github.com/repos/{repo}/commits/{ref}'))['sha']
        for path in paths:
            url = f'https://raw.githubusercontent.com/{repo}/{commit}/{path}'
            response = get(url)
            text = response.decode('utf-8')
            filename = platform + '-' + Path(path).name
            (target / filename).write_bytes(response)
            revision = re.search(r'revision\s+"([^"]+)"', text)
            version = re.search(r'oc-ext:openconfig-version\s+"([^"]+)"', text)
            sources.append(dict(id=filename, platform=platform, format=Path(path).suffix[1:],
                document_version='10.7.1' if platform == 'frr' else (version.group(1) if version else 'unspecified'),
                model_revision=revision.group(1) if revision else '', commit=commit, repository=repo,
                repository_path=path, source_url=f'https://github.com/{repo}/blob/{commit}/{path}',
                download_url=url, fetched_at=datetime.now(timezone.utc).isoformat(),
                sha256=hashlib.sha256(response).hexdigest(), filename=filename,
                content_kind='cli_documentation' if platform == 'frr' else 'yang_schema',
                compatibility='FRR 10.7.1 documentation; actual lab binary 10.7.1_git' if platform == 'frr'
                              else 'Vendor-neutral schema; not FRR CLI or proof of implementation support'))
    (BASE / 'sources-manifest.json').write_text(json.dumps(sources, indent=2) + '\n')
    print(json.dumps(sources, indent=2))


if __name__ == '__main__':
    main()
