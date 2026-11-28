"""Bound model context without changing frozen observations or silently removing a RAG variant."""
from copy import deepcopy


def select_observations(facts):
    alarming=[(i,f) for i,f in enumerate(facts) if f['anomaly']]
    primary=[row for row in alarming if row[1]['type'] in ('setting','physical')]
    primary.sort(key=lambda row:0 if row[1]['type']=='setting' else 1)
    if len(primary)>6:
        raise ValueError('too_many_observed_deviations')
    focus={f['router'] for _,f in primary if 'router' in f}
    focus.update(ep['router'] for _,f in primary if f['type']=='physical' for ep in f['endpoints'])
    protocols=[row for row in alarming if row[1]['type']=='protocol']
    protocols.sort(key=lambda row:row[1]['router'] not in focus)
    # All direct deviations are retained. Repetitive downstream symptoms are supporting context.
    chosen=primary+protocols[:1]
    return chosen or list(enumerate(facts))[:1],alarming


def model_documents(docs):
    # Full citations/hashes remain frozen alongside this projection, outside model token budget.
    return [{k:doc[k] for k in ('content','content_kind','document_version') if k in doc} for doc in docs]


def _table(rows):
    if not rows:return {'columns':[],'rows':[]}
    if not all(isinstance(row,dict) and set(row)==set(rows[0]) for row in rows):return deepcopy(rows)
    columns=sorted(rows[0])
    return {'columns':columns,'rows':[[deepcopy(row[k]) for k in columns] for row in rows]}


def compact_graph(graph):
    """Lossless tables for repeated edge fields; retain every edge, value and derivation field."""
    out=deepcopy(graph)
    if isinstance(graph.get('links'),dict):
        out['links']=_table([{'link_key':key,**value} for key,value in graph['links'].items()])
    if isinstance(graph.get('sessions'),list):out['sessions']=_table(graph['sessions'])
    return out
