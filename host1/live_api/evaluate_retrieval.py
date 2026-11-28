"""Offline Host 1 retrieval set/evaluation. Never imported by the live agent."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from .capture import ROOT, write

# Questions describe observations. Labels/relevance are evaluator metadata only.
PROMPTS={
 'mtu_mismatch':('OSPF tetap ExStart pada {link}, kedua interface UP. Pemeriksaan apa yang dijelaskan dokumentasi?', 'OSPF stays in ExStart on {link} while interfaces are UP. Which checks are documented?', [['mtu','exstart'],['mtu','mismatch']]),
 'link_down':('Interface pada {link} berstatus administratively DOWN dan peer terputus. Bagaimana memeriksa interface?', 'An interface on {link} is administratively DOWN and its peer disconnects. How should the interface be checked?', [['shutdown'],['interface','link']]),
 'ospf_hello_mismatch':('Pada {link}, log OSPF melaporkan hello interval tidak cocok dan neighbor hilang. Bagaimana memeriksanya?', 'On {link}, OSPF reports incompatible hello intervals and loses its neighbor. What should be checked?', [['hello-interval'],['hello','interval']]),
 'ospf_area_mismatch':('Pada {link}, OSPF menolak paket karena area ID berbeda. Konfigurasi apa yang perlu diperiksa?', 'OSPF rejects packets on {link} because area IDs differ. Which configuration should be checked?', [['area','interface']]),
 'ospf_auth_mismatch':('OSPF pada {link} melaporkan authentication mismatch. Bagaimana memeriksa konfigurasi autentikasi?', 'OSPF on {link} reports authentication mismatch. How is authentication configuration checked?', [['authentication'],['message-digest']]),
 'bgp_neighbor_shutdown':('Peer BGP pada {link} berada Idle (Admin), sementara interface UP. Apa arti state itu?', 'The BGP peer on {link} is Idle (Admin) while its interface is UP. What does this state indicate?', [['neighbor','shutdown']]),
 'bgp_wrong_remote_as':('BGP OPEN pada {link} ditolak dengan Bad Peer AS. Parameter peer apa yang harus dibandingkan?', 'The BGP OPEN on {link} is rejected with Bad Peer AS. Which peer parameter should be compared?', [['remote-as'],['remote','as']]),
 'bgp_inbound_filter':('Sesi BGP pada {link} Established tetapi prefix service tidak diterima melalui peer ini. Bagaimana memeriksa kebijakan inbound?', 'BGP on {link} is Established but a service prefix is not received through this peer. How is inbound policy inspected?', [['route-map'],['prefix-list']]),
 'bgp_missing_network':('Prefix service lokal pada {link} ada di tabel connected tetapi tidak diiklankan BGP. Bagaimana memeriksa originasi prefix?', 'A local service prefix at {link} is connected but not advertised by BGP. How is prefix origination checked?', [['network','bgp']]),
 'wrong_ip_address':('Interface pada {link} UP tetapi alamat IPv4 tidak berada dalam subnet peer yang dirancang. Bagaimana memeriksa alamat?', 'An interface on {link} is UP but its IPv4 address is outside the designed peer subnet. How should addressing be inspected?', [['ip address'],['interface','address']]),
}

def build_set():
    import yaml
    path=ROOT/'faults/host1.yaml';catalog=yaml.safe_load(path.read_text())
    rows=[]
    for fault in catalog['faults']:
        idq,enq,groups=PROMPTS[fault['class']]
        for lang,template in [('id',idq),('en',enq)]:
            rows.append(dict(query_id=fault['id']+'-'+lang,fault_id=fault['id'],language=lang,
                fault_class=fault['class'],question=template.format(link=fault['link']),relevance_groups=groups))
    return dict(version=1,catalog_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        scope='Offline retrieval evaluation only; keyword relevance proxy, not independent human relevance or agent accuracy.',questions=rows)

def evaluate(testset,output,live_context=False,only_mode=None):
    import yaml
    from knowledge.retriever import query
    from knowledge.quality_gate import citation
    data=yaml.safe_load(Path(testset).read_text());output=Path(output);output.mkdir(parents=True,exist_ok=False)
    current=hashlib.sha256((ROOT/'faults/host1.yaml').read_bytes()).hexdigest()
    if current!=data['catalog_sha256']:raise ValueError('Retrieval testset catalog changed')
    rows=[]
    modes=('dense','hybrid','hybrid_verified_expansion') if live_context else ('dense','hybrid')
    if only_mode:modes=(only_mode,)
    for mode in modes:
        for q in data['questions']:
            if mode=='hybrid_verified_expansion':
                from .retrieval import retrieve
                docs=retrieve(q['question'],limit=5,full_text=True)
                found={'hits':[dict(id=str(i),text=d['content'],metadata=d) for i,d in enumerate(docs)]}
            else:
                found=query(q['question'],platform='frr',top_k=5,mode=mode)
                for h in found['hits']:citation(h,'frr')
            relevant=[h['id'] for h in found['hits'] if any(all(term in h['text'].lower() for term in group) for group in q['relevance_groups'])]
            row={**q,'mode':mode,'hit_at_5':bool(relevant),'relevant_ids':relevant,'retrieval':found};rows.append(row)
            with (output/'rows.jsonl').open('a',encoding='utf-8') as handle:
                handle.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(mode+': '+str(sum(r['hit_at_5'] for r in rows if r['mode']==mode))+'/'+str(len(data['questions'])),flush=True)
    summary=dict(catalog_sha256=current,query_count=len(data['questions']),modes={m:{'hits':sum(r['hit_at_5'] for r in rows if r['mode']==m),'total':len(data['questions'])} for m in modes},scope=data['scope'])
    write(output/'summary.json',summary);print(json.dumps(summary,indent=2),flush=True);return summary

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write-testset',action='store_true');ap.add_argument('--live-context',action='store_true');ap.add_argument('--only-mode',choices=['dense','hybrid','hybrid_verified_expansion']);ap.add_argument('--testset',type=Path,default=ROOT/'data/retrieval_host1_testset.yaml');ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    if args.write_testset:
        import yaml
        args.testset.write_text(yaml.safe_dump(build_set(),allow_unicode=True,sort_keys=False),encoding='utf-8')
    if args.output:
        if not args.output.resolve().is_relative_to(ROOT/'private'):ap.error('Evaluation output must stay private')
        evaluate(args.testset,args.output,args.live_context,args.only_mode)

if __name__=='__main__':main()
