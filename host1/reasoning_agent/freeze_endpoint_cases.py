"""Preregister paired order x citation-ID tests before endpoint-extractor development."""
from datetime import datetime, timezone
import hashlib
import json
import random
import sys
from knowledge.evidence import ROOT, local_path

def id_map(seed):
    rng=random.Random(seed);pool=rng.sample(range(100,999),6)
    return {key:'R'+str(number) for key,number in zip(('D1','T1','T2','G1','L1','L2'),pool)}

def main(directory):
    directory=local_path(directory);directory.mkdir(parents=True,exist_ok=False)
    source=ROOT/'data/host1/evidence-retrieval/replay-final-20261119'
    development=[];matrix=[];controls=[];expected={}
    def add(target,link,phase,ident,options,role,factors=None):
        path=source/(link+'-'+phase+'.json')
        expected[ident]=dict(state='fault' if phase=='down' else 'healthy',phase='fault' if phase=='down' else 'baseline' if phase=='before' else 'recovered',
                            target=('r1:eth1' if link=='L12' else 'r3:eth4') if phase=='down' else None)
        target.append(dict(id=ident,bundle=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           options=options,role=role,link=link,factors=factors))
    for index,link in enumerate(('L12','L35')):
        add(development,link,'down','d'+str(len(development)+1),{},'known_control')
        add(development,link,'down','d'+str(len(development)+1),dict(reverse_endpoints=True,opaque_ids=True),'known_failed_layout')
        mapping=id_map(73191+index)
        for reverse in (False,True):
            for renamed in (False,True):
                options=dict(reverse_endpoints=reverse)
                if renamed:options['citation_map']=mapping
                add(matrix,link,'down','f'+str(len(matrix)+1),options,
                    'old_layout_control' if not reverse and not renamed else 'new_factorial_layout',
                    dict(order='reversed' if reverse else 'normal',citation='fresh' if renamed else 'native'))
        for phase in ('before','restored'):
            add(controls,link,phase,'c'+str(len(controls)+1),
                dict(reverse_endpoints=True,citation_map=id_map(83943+index)), 'new_id_healthy_regression')
    random.Random(48031).shuffle(matrix);random.Random(73115).shuffle(controls)
    files=dict(development=development,factorial=matrix,controls=controls,expected=expected)
    hashes={}
    for key,value in files.items():
        name=key+'.json';data=(json.dumps(value,indent=2)+'\n').encode();(directory/name).write_bytes(data)
        hashes[name]=hashlib.sha256(data).hexdigest()
    report=dict(frozen_at=datetime.now(timezone.utc).isoformat(),hashes=hashes,
        design='Paired 2x2 endpoint order x citation ID on L12/L35 down; same opaque map in both order cells per link.',
        scope='Two stored fault traces, single run/cell; six new factorial layouts plus two known controls, four new-ID healthy regressions.',
        policy='Develop only on four known layouts. Freeze candidate before paired grouped/bound factorial and healthy controls; no tuning on final results.')
    (directory/'preregistered.json').write_text(json.dumps(report,indent=2))
    (directory/'legacy-temporal.py').write_bytes((ROOT/'host1/reasoning_agent/temporal.py').read_bytes())
    print(json.dumps(report,indent=2))

if __name__=='__main__':main(sys.argv[1])
