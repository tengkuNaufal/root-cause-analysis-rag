"""Freeze perturbation definitions and expected labels before model development."""
from datetime import datetime, timezone
import hashlib
import json
import random
import sys
from knowledge.evidence import ROOT, local_path

def main(directory):
    directory=local_path(directory);directory.mkdir(parents=True,exist_ok=False)
    source=ROOT/'data/host1/evidence-retrieval/replay-final-20261119'
    development=[];variations=[];expected={}
    def case(link,phase,ident,**options):
        path=source/(link+'-'+phase+'.json')
        coverage=options.get('history','all')
        label='fault' if phase=='down' else ('undetermined' if coverage!='all' else 'recovered' if phase=='restored' else 'baseline')
        expected[ident]=dict(state='fault' if phase=='down' else 'healthy',phase=label,
                             target=('r1:eth1' if link=='L12' else 'r3:eth4') if phase=='down' else None)
        return dict(id=ident,bundle=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),options=options)
    for link in ('L12','L35'):
        for phase in ('before','down','restored'):
            development.append(case(link,phase,'d'+str(len(development)+1)))
        for phase,options in [('before',dict(reverse_endpoints=True,opaque_ids=True)),
                              ('down',dict(reverse_endpoints=True,opaque_ids=True)),
                              ('restored',dict(reverse_events=True,opaque_ids=True)),
                              ('restored',dict(history='down_only',opaque_ids=True)),
                              ('restored',dict(history='none',reverse_endpoints=True,opaque_ids=True)),
                              ('down',dict(reverse_events=True,opaque_ids=True,doc_last=True))]:
            variations.append(case(link,phase,'u'+str(len(variations)+1),**options))
    random.Random(20261120).shuffle(variations)
    files={'development.json':development,'variations.json':variations,'expected.json':expected}
    hashes={}
    for name,value in files.items():
        data=(json.dumps(value,indent=2)+'\n').encode();(directory/name).write_bytes(data)
        hashes[name]=hashlib.sha256(data).hexdigest()
    report=dict(frozen_at=datetime.now(timezone.utc).isoformat(),hashes=hashes,
        development_cases=6,unrun_perturbations=12,
        scope='Assistant-designed presentation/visibility perturbations of stored traces; not independent network faults or human labels',
        policy='Develop on development.json. Freeze implementation before first variations run; do not call reused cases held-out after tuning.')
    (directory/'preregistered.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main(sys.argv[1])
