"""Real localhost HTTP tests with explicitly simulated model responses."""
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from knowledge.evidence import ROOT, instant
from reasoning_agent.api import ReplayService, handler

class SimulatedModel:
    def generate(self,request):
        text=request['prompt'].split('<|start_header_id|>user<|end_header_id|>\n\n')[1].split('<|eot_id|>')[0]
        data=json.loads(text);title=request['format']['title']
        if title=='EndpointState':
            row=data['source_endpoint'];value={k:row[k] for k in ('admin_up','carrier_up','peer_state')}
        elif title=='HistoryContext':
            value=dict(physical=data['graph']['physical'],history_complete=data['history']['complete'],
                events_time_order=[x['event'] for x in sorted(data['history']['events'],key=lambda x:instant(x['time']))])
        elif title=='Phase':
            phase='fault' if data['current_relation']=='UNEQUAL' else 'recovered' if 'UNEQUAL' in data['earlier_relations'] else 'baseline' if data['coverage']=='complete' else 'undetermined'
            value=dict(phase=phase)
        else:
            obs=data['model_observations']
            phase='fault' if obs['admin_down'] else 'recovered' if obs['events']==['DOWN','UP'] and obs['coverage']=='complete' else 'baseline' if obs['coverage']=='complete' else 'undetermined'
            value=dict(phase=phase)
        return dict(done=True,done_reason='stop',prompt_eval_count=100,eval_count=15,response=json.dumps(value))

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
        cls.output=ROOT/'data/host1/agent-api-tests'/stamp
        cls.service=ReplayService(cls.output,transport=SimulatedModel())
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler(cls.service))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,path,body=None,method=None,raw=None,headers=None):
        data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        request=urllib.request.Request(self.url+path,data=data,method=method,
            headers=headers or ({'Content-Type':'application/json'} if data is not None else {}))
        try:
            with urllib.request.urlopen(request,timeout=60) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as exc:return exc.code,json.load(exc)
    def test_health_is_not_model_readiness_claim(self):
        status,value=self.request('/health');self.assertEqual(status,200)
        self.assertEqual(value['model_readiness'],'not_probed');self.assertFalse(value['execution_allowed'])
    def test_catalog_has_no_source_paths(self):
        status,value=self.request('/v1/scenarios');self.assertEqual(status,200);self.assertEqual(len(value['scenarios']),16)
        self.assertNotIn('input',value['scenarios'][0])
    def test_mtu_result_citation_retrieval_and_timing(self):
        status,value=self.request('/v1/replays',dict(scenario_id='mtu.l35.fault'))
        self.assertEqual(status,201);self.assertEqual(value['phase'],'fault');self.assertEqual(value['model']['requests'],1)
        self.assertGreater(value['timing']['total_seconds'],0);self.assertFalse(value['execution_allowed'])
        self.assertEqual(value['result']['proposed_patch'],[])
        evidence=value['evidence'][0];self.assertNotIn('source_path',evidence)
        status,found=self.request(evidence['url']);self.assertEqual(status,200);self.assertEqual(found,evidence)
        status,found=self.request('/v1/runs/'+value['run_id']);self.assertEqual(status,200);self.assertEqual(found,value)
        known={e['id'] for e in value['evidence']}
        self.assertTrue(all(set(c['evidence_ids'])<=known for c in value['citations']))
    def test_temporal_route_uses_bound_four_model_calls(self):
        status,value=self.request('/v1/replays',dict(scenario_id='temporal.l12.fault'))
        self.assertEqual(status,201);self.assertEqual(value['phase'],'fault');self.assertEqual(value['model']['requests'],4)
        self.assertFalse(value['synthetic'])
    def test_negative_source_is_business_abstention(self):
        status,value=self.request('/v1/replays',dict(scenario_id='mtu.l12.invalid-mtu'))
        self.assertEqual(status,201);self.assertEqual(value['status'],'abstain')
        self.assertFalse(value['model']['called']);self.assertEqual(value['evidence'],[])
    def test_unknown_scenario(self):self.assertEqual(self.request('/v1/replays',dict(scenario_id='not.registered'))[0],404)
    def test_arbitrary_path_field_rejected(self):
        self.assertEqual(self.request('/v1/replays',dict(scenario_id='mtu.l12.fault',path='/etc/passwd'))[0],400)
    def test_execution_field_rejected(self):
        self.assertEqual(self.request('/v1/replays',dict(scenario_id='mtu.l12.fault',execute=True))[0],400)
    def test_malformed_duplicate_and_wrong_shape_json(self):
        for raw in (b'{',b'{"scenario_id":"mtu.l12.fault","scenario_id":"mtu.l35.fault"}',b'[]',b'{"scenario_id":true}'):
            self.assertEqual(self.request('/v1/replays',raw=raw)[0],400)
    def test_content_type_and_body_limit(self):
        self.assertEqual(self.request('/v1/replays',raw=b'{}',headers={'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('/v1/replays',raw=b'x'*4097)[0],413)
    def test_no_filesystem_or_executor_routes(self):
        for path in ('/etc/passwd','/v1/execute','/v1/runs/'+'a'*32+'/evidence/../../runtime'):
            self.assertEqual(self.request(path)[0],404)
        self.assertEqual(self.request('/v1/replays',{},method='DELETE')[0],405)
    def test_unknown_run_and_evidence(self):
        self.assertEqual(self.request('/v1/runs/'+'a'*32)[0],404)
    def test_busy_rejects_second_inference(self):
        self.service.lock.acquire()
        try:
            status,value=self.request('/v1/replays',dict(scenario_id='mtu.l12.fault'))
            self.assertEqual(status,503);self.assertEqual(value['error']['code'],'agent_busy')
        finally:self.service.lock.release()
    def test_pinned_catalog_change_rejected(self):
        original=self.service.catalog_ref['sha256'];self.service.catalog_ref['sha256']='0'*64
        try:self.assertEqual(self.request('/v1/replays',dict(scenario_id='mtu.l12.fault'))[0],409)
        finally:self.service.catalog_ref['sha256']=original
    def test_changed_evidence_rejected_without_modifying_source(self):
        status,value=self.request('/v1/replays',dict(scenario_id='mtu.l12.baseline'));self.assertEqual(status,201)
        evidence=value['evidence'][0];private=self.service.records[value['run_id']]['sources'][evidence['id']]
        original=private['sha256'];private['sha256']='0'*64
        try:self.assertEqual(self.request(evidence['url'])[0],409)
        finally:private['sha256']=original
    def test_model_outage_is_service_error_not_diagnosis(self):
        class Offline:
            def generate(self,request):raise urllib.error.URLError('Simulated backend unavailable')
        original=self.service.transport;self.service.transport=Offline()
        try:
            status,value=self.request('/v1/replays',dict(scenario_id='mtu.l12.fault'))
            self.assertEqual(status,503);self.assertEqual(value['error']['code'],'model_unavailable')
        finally:self.service.transport=original

if __name__=='__main__':unittest.main()
