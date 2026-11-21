"""Freeze supplementary primary references, separate from the FRR CLI/YANG index."""
from datetime import datetime, timezone
import hashlib
import json
from urllib.request import Request, urlopen
from knowledge.evidence import ROOT

COMMIT = 'f8c0b08dcb0c78f9e42b9b86ae70b049e4e617c1'
SOURCES = [
 ('frr-ospf-vty.c', f'https://raw.githubusercontent.com/FRRouting/frr/{COMMIT}/ospfd/ospf_vty.c', 'frr_source_code', COMMIT),
 ('frr-ospf-packet.c', f'https://raw.githubusercontent.com/FRRouting/frr/{COMMIT}/ospfd/ospf_packet.c', 'frr_source_code', COMMIT),
 ('rfc2328.txt', 'https://www.rfc-editor.org/rfc/rfc2328.txt', 'protocol_standard', 'RFC2328'),
 ('linux-netdevices.rst', 'https://raw.githubusercontent.com/torvalds/linux/v6.3/Documentation/networking/netdevices.rst', 'linux_kernel_documentation', 'v6.3'),
]

def main():
    out = ROOT / 'host1/knowledge/supplemental-mtu'
    out.mkdir(exist_ok=False)
    manifest = []
    for name, url, kind, version in SOURCES:
        with urlopen(Request(url, headers={'User-Agent':'NetworkLab-study/1.0'}), timeout=45) as response:
            body = response.read()
        (out/name).write_bytes(body)
        manifest.append(dict(filename=name,url=url,content_kind=kind,version=version,
                             fetched_at=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(body).hexdigest()))
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(name, len(body),flush=True)

if __name__ == '__main__':
    main()
