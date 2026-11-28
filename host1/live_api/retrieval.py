"""Live-only query normalization and typed verified-document expansion; shared Chroma is unchanged."""
import hashlib
import json
import re
from .capture import ROOT

def query_from_facts(facts):
    terms=[]
    for f in facts:
        key=f.get('key','')
        if f['type']=='physical':
            obs=[e['observed'] for e in f['endpoints'] if e['observed']]
            terms.append('interface shutdown no shutdown admin down' if any(not o['admin_up'] for o in obs) else 'OSPF MTU mtu-ignore interface')
        elif key.endswith('/ospf_hello') or key.endswith('/ospf_dead'):terms.append('OSPF hello-interval dead-interval')
        elif key.endswith('/ospf_area'):terms.append('OSPF interface area')
        elif 'ospf_auth' in key or key.endswith('/ospf_key_present'):terms.append('OSPF authentication message-digest-key')
        elif key.endswith('/remote_as'):terms.append('BGP neighbor remote-as')
        elif key.endswith('/shutdown'):terms.append('BGP neighbor shutdown')
        elif key.startswith(('route_map/','prefix_list/')):terms.append('BGP inbound route-map prefix-list')
        elif key=='bgp/networks':terms.append('BGP network prefix advertisement')
        elif key.endswith('/addresses'):terms.append('interface ip address subnet')
    return 'FRR '+ ' '.join(dict.fromkeys(terms or ['OSPF BGP session troubleshooting']))

def _pinned(folder,manifest,name,start,end):
    entry=next(e for e in manifest if e['filename']==name)
    data=(folder/name).read_bytes()
    if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Pinned live reference changed')
    lines=data.decode('utf-8').splitlines()
    return dict(content='\n'.join(lines[start-1:end]),citation_url=entry.get('source_url',entry.get('url')),
        original_source_sha256=entry['sha256'],original_locator=f'lines:{start}-{end}',
        content_kind=entry['content_kind'],document_version=entry.get('document_version',entry.get('version')),
        selection_origin='verified_live_expansion')

def excerpt(text,query,width=400):
    tokens={t for t in re.findall(r'[a-z][a-z0-9_-]+',query.lower()) if len(t)>3 or t in ('mtu','ospf','bgp')}
    positions=[0]
    for token in tokens:
        positions.extend(m.start() for m in list(re.finditer(re.escape(token),text.lower()))[:20])
    choices=[]
    for pos in positions:
        start=max(0,pos-80);end=min(len(text),start+width);body=text[start:end].lower()
        score=sum((3 if '-' in t or t in ('mtu','exstart','shutdown','authentication') else 1) for t in tokens if t in body)
        choices.append((-score,start,end))
    _,start,end=min(choices)
    return start,end


def retrieve(query,limit=2,full_text=False):
    from knowledge.retriever import query as search
    from knowledge.quality_gate import citation
    hits=search(query,platform='frr',top_k=5,mode='hybrid')['hits'];base=[]
    for h in hits:
        citation(h,'frr');text=h['text'];start,end=(0,len(text)) if full_text else excerpt(text,query)
        base.append(dict(content=text[start:end],citation_url=h['metadata']['citation_url'],
            original_source_sha256=h['metadata']['sha256'],chunk_id=h['id'],chunk_chars=[start,end],
            content_kind=h['metadata']['content_kind'],selection_origin='chroma_hybrid'))
    extras=[];q=query.lower()
    if 'mtu' in q or 'exstart' in q:
        folder=ROOT/'host1/knowledge/supplemental-mtu';manifest=json.loads((folder/'manifest.json').read_text())
        # Source code proves a mismatch check exists, not that bypassing it is a valid repair.
        extras.append(_pinned(folder,manifest,'frr-ospf-vty.c',9853,9860))
        extras.append(_pinned(folder,manifest,'rfc2328.txt',4925,4929))
    if ('neighbor' in q and 'shutdown' in q) or ('idle' in q and 'admin' in q):
        folder=ROOT/'host1/knowledge/sources';manifest=json.loads((ROOT/'host1/knowledge/sources-manifest.json').read_text())
        extras.append(_pinned(folder,manifest,'frr-bgp.rst',1788,1800))
    return (extras+base)[:limit]
