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
            endpoints=[e for e in f['endpoints'] if e.get('observed')]
            if any(not e['observed']['admin_up'] for e in endpoints):
                terms.append('interface shutdown no shutdown admin down')
            if any(e['expected_ipv4'] not in e['observed']['ipv4'] for e in endpoints):
                terms.append('interface ip address subnet')
            if any(e['observed']['mtu'] != f['expected_mtu'] for e in endpoints):
                terms.append('OSPF MTU interface mismatch')
        elif key.endswith('/ospf_hello') or key.endswith('/ospf_dead'):terms.append('OSPF hello-interval dead-interval')
        elif key.endswith('/ospf_area'):terms.append('OSPF interface area')
        elif 'ospf_auth' in key or key.endswith(('/ospf_key_present','/ospf_key_ids')):terms.append('OSPF authentication message-digest-key')
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
    # RFC form feeds are page separators, not source line boundaries.
    lines=data.decode('utf-8').split('\n')
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


def command_reference(query):
    """A verified command reference selected by observed query terms, never a fault ID."""
    q=query.lower()
    choices=[('remote-as','frr-bgp.rst',1695,1710),
             ('network prefix advertisement','frr-bgp.rst',1225,1240),
             ('inbound route-map','frr-bgp.rst',2443,2460),
             ('hello-interval','frr-ospfd.rst',732,747),
             ('ospf interface area','frr-ospfd.rst',626,637),
             ('authentication','frr-ospfd.rst',648,675),
             ('ip address subnet','frr-zebra.rst',174,182),
             ('admin down','frr-zebra.rst',168,173)]
    selected=next(((name,start,end) for term,name,start,end in choices if term in q),None)
    if selected is None:return None
    folder=ROOT/'host1/knowledge/sources'
    manifest=json.loads((ROOT/'host1/knowledge/sources-manifest.json').read_text())
    return _pinned(folder,manifest,*selected)


def retrieve(query,limit=2,full_text=False,*,search=None,verify=None):
    if search is None:
        from knowledge.retriever import query as search
    if verify is None:
        from knowledge.quality_gate import citation as verify
    hits=search(query,platform='frr',top_k=5,mode='hybrid')['hits'];base=[]
    for h in hits:
        verify(h,'frr');text=h['text'];start,end=(0,len(text)) if full_text else excerpt(text,query)
        base.append(dict(content=text[start:end],citation_url=h['metadata']['citation_url'],
            original_source_sha256=h['metadata']['sha256'],chunk_id=h['id'],chunk_chars=[start,end],
            content_kind=h['metadata']['content_kind'],selection_origin='chroma_hybrid'))
    extras=[];q=query.lower()
    if 'mtu' in q or 'exstart' in q:
        folder=ROOT/'host1/knowledge/supplemental-mtu';manifest=json.loads((folder/'manifest.json').read_text())
        # Source code proves a mismatch check exists, not that bypassing it is a valid repair.
        extras.append(_pinned(folder,manifest,'frr-ospf-packet.c',1224,1232))
        extras.append(_pinned(folder,manifest,'rfc2328.txt',4925,4929))
    if ('neighbor' in q and 'shutdown' in q) or ('idle' in q and 'admin' in q):
        folder=ROOT/'host1/knowledge/sources';manifest=json.loads((ROOT/'host1/knowledge/sources-manifest.json').read_text())
        extras.append(_pinned(folder,manifest,'frr-bgp.rst',1788,1800))
    reference=command_reference(query)
    # Specific configuration references take priority over incidental physical symptoms.
    # Retain a real Chroma hit alongside the pinned CLI reference whenever available.
    return ([reference]+base if reference is not None else extras+base)[:limit]
