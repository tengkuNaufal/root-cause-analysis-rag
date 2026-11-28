"""Offline budgets, lossless graph projection and exact evidence bindings."""
from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from .context import select_observations, compact_graph, model_documents
from .agent import CONTEXT, OUTPUT, model_prompt
from .models import canonical
from .test_agent import engine,run_engine


class ContextTests(unittest.TestCase):
    def test_all_causal_deviations_survive_and_only_repetitive_protocols_are_limited(self):
        facts=[dict(type='protocol',router='r'+str(n),anomaly=True) for n in range(1,7)]
        facts.append(dict(type='setting',router='r5',anomaly=True,key='bgp/networks',expected=['192.0.2.0/24'],observed=[]))
        before=deepcopy(facts);chosen,alarms=select_observations(facts)
        self.assertEqual([i for i,_ in chosen],[6,4]);self.assertEqual(len(alarms),7)
        self.assertEqual(facts,before)

    def test_too_many_direct_deviations_fail_closed_instead_of_hiding_one(self):
        with self.assertRaisesRegex(ValueError,'too_many'):
            select_observations([dict(type='setting',router='r1',anomaly=True) for _ in range(7)])

    def test_graph_tables_preserve_every_edge_and_state(self):
        graph=dict(links={'L12':dict(endpoints=['r1','r2'],mtu=1500,state='up')},
            sessions=[dict(a='r1',b='r2',kind='ospf',state='Full'),dict(a='r2',b='r1',kind='ospf',state='Init')],
            derived_from_snapshot='0'*64,semantics='Observed directed edges')
        before=deepcopy(graph);packed=compact_graph(graph)
        self.assertEqual(graph,before)
        for field in ('links','sessions'):
            recovered=[dict(zip(packed[field]['columns'],row)) for row in packed[field]['rows']]
            if field=='links':
                restored={row.pop('link_key'):row for row in recovered}
                self.assertEqual(restored,graph[field])
            else:self.assertEqual(recovered,graph[field])
        self.assertEqual(packed['derived_from_snapshot'],graph['derived_from_snapshot'])

    def test_graph_optional_fields_are_not_changed_to_null(self):
        graph={'sessions':[dict(a='r1',state='Full'),dict(a='r2')]}
        self.assertEqual(compact_graph(graph)['sessions'],graph['sessions'])

    def test_document_projection_keeps_body_and_type_without_spending_context_on_citation_metadata(self):
        doc=dict(content='ip address ADDRESS/PREFIX',content_kind='cli_documentation',document_version='10.7.1',
                 citation_url='https://example.invalid/reference',original_source_sha256='0'*64)
        self.assertEqual(model_documents([doc]),[{k:doc[k] for k in ('content','content_kind','document_version')}])

    def test_projected_evidence_is_an_exact_fragment_of_its_frozen_source(self):
        eng=engine()
        with tempfile.TemporaryDirectory() as tmp:
            job=run_engine(eng,tmp,'graph_rag')
            directory=next(Path(tmp).iterdir())
            refs=json.loads((directory/'evidence-index.json').read_text())
            for ref in refs:
                value=json.loads((directory/ref['file']).read_text())
                for token in ref['payload']['locator'].split('/')[1:]:
                    value=value[int(token)] if isinstance(value,list) else value[token]
                self.assertEqual(canonical(value).decode(),ref['payload']['content'])
            graph=json.loads((directory/'graph.json').read_text())
            self.assertIn('sessions',graph);self.assertIn('model_graph',graph)
            docs=json.loads((directory/'documentation.json').read_text())
            self.assertIn('citation_url',docs['documentation'][0])
            self.assertNotIn('citation_url',docs['model_documentation'][0])
            self.assertEqual({e['kind'] for e in job['evidence']},{'telemetry','documentation','graph'})
            self.assertLessEqual(len(eng.model.calls[0]['prompt'].encode())+OUTPUT+128,CONTEXT)

    def test_budget_can_omit_protocol_context_but_not_causal_or_rag_evidence(self):
        eng=engine();original=eng.capture.capture
        def capture(directory):
            value=original(directory)
            # Large repeated downstream symptoms must not crowd out the measured MTU deviation.
            value['facts']['observations'].append(dict(type='protocol',router='r1',anomaly=True,detail='x'*6000))
            return value
        eng.capture.capture=capture
        eng.graph_builder=lambda *_:dict(links={},sessions=[],derived_from_snapshot='0'*64)
        with tempfile.TemporaryDirectory() as tmp:
            job=run_engine(eng,tmp,'graph_rag')
            directory=next(Path(tmp).iterdir())
            policy=json.loads((directory/'context-selection.json').read_text())
            self.assertTrue(policy['omitted_protocol_evidence_ids'])
            self.assertEqual({e['kind'] for e in job['evidence']},{'telemetry','documentation','graph'})
            refs=json.loads((directory/'evidence-index.json').read_text())
            telemetry=[json.loads(r['payload']['content']) for r in refs if r['payload']['kind']=='telemetry']
            self.assertTrue(all(f['type']=='physical' for f in telemetry))
            self.assertEqual(job['provenance']['actual_variant'],'graph_rag')
