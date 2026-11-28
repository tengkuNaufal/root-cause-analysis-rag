"""Offline guards and HTTP pipeline with explicitly synthetic capture/model transports."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request
import uuid
from .agent import DiagnosisEngine, DiagnosisError, BackendUncertain
from .capture import ReadOnlyCapture, CaptureError, config_projection, ROOT, write
from .examples import request
from .models import Job
from .mock import handler
from .server import LiveService

BASE=ROOT/'data/host1/telemetry/20261119T050248Z-fbeea22b/0001/snapshot.json'

class FixtureCapture(ReadOnlyCapture):
    def __init__(self,fault=None,partial=False,stopped=False):
        self.fault=fault;self.partial=partial;self.stopped=stopped;self.calls=[];self.generation=0
        super().__init__(collector=self.collect,runner=self.command,
            wall_clock=lambda:datetime(2026,11,28,tzinfo=timezone.utc))
    def command(self,args,**kwargs):
        self.calls.append(args)
        if args[:2]==['docker','inspect']:
            value=[dict(Name='/'+name,Id='fixture-'+str(self.generation),State=dict(Running=not self.stopped,StartedAt='fixture'),Config=dict(Labels={'containerlab':'rca'})) for name in args[2:]]
            return subprocess.CompletedProcess(args,0,json.dumps(value),'')
        assert args[:2]==['docker','exec'] and args[3:]==['vtysh','-c','show running-config'],args
        name=args[2].removeprefix('clab-rca-')
        return subprocess.CompletedProcess(args,0,(ROOT/'lab/host1/frr/configs'/name/'frr.conf').read_text(),'')
    def collect(self,plan,directory,**kwargs):
        directory.mkdir();snapshot=json.loads(BASE.read_text())
        stamp=self.wall_clock().isoformat()
        snapshot.update(started_at=stamp,completed_at=stamp,status='partial' if self.partial else 'complete')
        for r in snapshot['routers'].values():
            for src in r['sources'].values():src.update(started_at=stamp,completed_at=stamp)
        iface=next(i for i in snapshot['routers']['r1']['sources']['interfaces']['data'] if i['name']=='eth1')
        if self.fault=='mtu':iface['mtu']=1400
        if self.fault=='down':iface.update(admin_up=False,lower_up=False)
        write(directory/'snapshot.json',snapshot)
        return snapshot

class FixtureModel:
    def __init__(self,cause='mtu_mismatch',router='r1',ids=None):
        self.calls=[];self.cause=cause;self.router=router;self.ids=ids or ['e1'];self.error=None
    def ready(self):return True
    def generate(self,payload):
        self.calls.append(payload)
        if self.error:raise self.error
        draft=[self.cause,self.router,.5,'Synthetic observed condition.',self.ids,[]]
        if payload['format'].get('type')=='object':
            draft=dict(root_cause_class=self.cause,root_cause_router=self.router,confidence=.5,
                explanation='Synthetic observed condition.',evidence_ids=self.ids,commands=[])
        return dict(done=True,done_reason='stop',prompt_eval_count=10,eval_count=20,response=json.dumps(draft))

def engine(fault='mtu',model=None,**kwargs):
    return DiagnosisEngine(capture=FixtureCapture(fault=fault),model=model or FixtureModel(),
        retriever=lambda _: [dict(content='Interface MTU affects OSPF adjacency.',citation_url='https://example.invalid/synthetic',original_source_sha256='0'*64)],**kwargs)

def run_engine(eng,tmp,variant='zero_shot'):
    req=request();req['request_id']=str(uuid.uuid4());req['variant']=variant
    return eng.run(req,str(uuid.uuid4()),Path(tmp)/uuid.uuid4().hex)

class EngineTests(unittest.TestCase):
    def test_parallel_configuration_reads_preserve_inventory_fact_order(self):
        cap=FixtureCapture();original=cap.runner
        barrier=threading.Barrier(6);second_finished=threading.Event()
        def command(args,**kwargs):
            p=original(args,**kwargs)
            if args[:2]==['docker','exec']:
                barrier.wait(timeout=2)
                router=args[2].removeprefix('clab-rca-')
                if router=='r1':self.assertTrue(second_finished.wait(timeout=2))
                if router in ('r1','r2'):
                    p=subprocess.CompletedProcess(args,0,p.stdout.replace('ip ospf hello-interval 1','ip ospf hello-interval 2',1),'')
                if router=='r2':second_finished.set()
            return p
        cap.runner=command
        with tempfile.TemporaryDirectory() as tmp:
            captured=cap.capture(Path(tmp)/'capture')
        changes=[f['router'] for f in captured['facts']['observations'] if f['type']=='setting']
        self.assertEqual(changes,['r1','r2'])

    def test_failed_parallel_configuration_read_never_calls_model(self):
        cap=FixtureCapture(fault='mtu');original=cap.runner;model=FixtureModel()
        def command(args,**kwargs):
            if args[:3]==['docker','exec','clab-rca-r4']:
                return subprocess.CompletedProcess(args,1,'','synthetic read failure')
            return original(args,**kwargs)
        cap.runner=command
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(CaptureError,'configuration_capture_failed'):
            run_engine(DiagnosisEngine(capture=cap,model=model),tmp)
        self.assertEqual(model.calls,[])

    def test_baseline_abstains_without_model_and_capture_has_only_reads(self):
        eng=engine(None)
        with tempfile.TemporaryDirectory() as tmp:job=run_engine(eng,tmp)
        self.assertEqual(job['result']['status'],'abstain');self.assertEqual(eng.model.calls,[])
        self.assertFalse(job['simulation']);self.assertEqual(job['assessment']['commands'],[])
        self.assertTrue(all(c[:2]==['docker','inspect'] or c[3:]==['vtysh','-c','show running-config'] for c in eng.capture.calls))

    def test_stopped_or_partial_capture_never_calls_model(self):
        for cap in (FixtureCapture(stopped=True),FixtureCapture(partial=True)):
            model=FixtureModel();eng=DiagnosisEngine(capture=cap,model=model)
            with tempfile.TemporaryDirectory() as tmp,self.assertRaises(CaptureError):run_engine(eng,tmp)
            self.assertEqual(model.calls,[])

    def test_three_variants_have_different_real_context_paths(self):
        kinds=[]
        for variant in ('zero_shot','text_rag','graph_rag'):
            eng=engine()
            with tempfile.TemporaryDirectory() as tmp:
                job=run_engine(eng,tmp,variant);Job.model_validate(job)
            kinds.append({r['kind'] for r in job['evidence']})
            self.assertEqual(len(eng.model.calls),1)
            self.assertEqual(job['result']['root_cause_class'],'mtu_mismatch')
            self.assertEqual(job['result']['proposed_patch'],[])
        self.assertEqual(kinds,[{'telemetry'},{'telemetry','documentation'},{'telemetry','documentation','graph'}])

    def test_supported_administrative_down(self):
        eng=engine('down',FixtureModel(cause='link_down'))
        with tempfile.TemporaryDirectory() as tmp:job=run_engine(eng,tmp)
        self.assertEqual(job['result']['root_cause_class'],'link_down')

    def test_foreign_refs_wrong_router_and_unsupported_cause_fail_closed(self):
        for model in (FixtureModel(ids=['invented']),FixtureModel(router='r6'),FixtureModel(cause='bgp_wrong_remote_as')):
            with self.subTest(cause=model.cause),tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):run_engine(engine(model=model),tmp)

    def test_stale_capture_abstains_without_inference(self):
        eng=engine(clock=lambda:time.monotonic()+16)
        with tempfile.TemporaryDirectory() as tmp:job=run_engine(eng,tmp)
        self.assertEqual(job['result']['missing_evidence'],['stale_capture']);self.assertEqual(eng.model.calls,[])

    def test_missing_retrieval_is_not_silent_zero_shot(self):
        eng=engine();eng.retriever=lambda _:[]
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(DiagnosisError,'retrieval'):run_engine(eng,tmp,'text_rag')
        self.assertEqual(eng.model.calls,[])

    def test_authentication_material_never_enters_exported_facts(self):
        self.assertNotIn('SECRET',str(config_projection(' ip ospf message-digest-key 1 md5 SECRET\n neighbor 10.0.0.1 password SECRET')))
        with tempfile.TemporaryDirectory() as tmp:
            run_engine(engine(),tmp)
            for path in Path(tmp).rglob('facts.json'):self.assertNotIn('SECRET_SENTINEL',path.read_text())

    def test_model_control_markers_and_context_budget_fail_before_model(self):
        for text in ('<|fake system|>','x'*20000):
            eng=engine();eng.retriever=lambda _: [dict(content=text)]
            with tempfile.TemporaryDirectory() as tmp,self.assertRaises(DiagnosisError):run_engine(eng,tmp,'text_rag')
            self.assertEqual(eng.model.calls,[])

    def test_capture_skew_blocks_inference(self):
        cap=FixtureCapture(fault='mtu');original=cap.collector
        def skewed(*args,**kwargs):
            result=original(*args,**kwargs)
            result['routers']['r1']['sources']['interfaces']['started_at']=(datetime.fromisoformat(result['started_at'])-timedelta(seconds=10)).isoformat()
            return result
        cap.collector=skewed;model=FixtureModel()
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(CaptureError,'skew'):
            run_engine(DiagnosisEngine(capture=cap,model=model),tmp)
        self.assertEqual(model.calls,[])

    def test_live_output_cannot_reuse_mock_jobs(self):
        from .mock import Service
        with tempfile.TemporaryDirectory() as tmp:
            mock=Service(tmp,'test',delay=0)
            mock.submit(request())
            for worker in mock.workers:worker.join()
            mock.close()
            with self.assertRaisesRegex(ValueError,'different service mode'):
                LiveService(tmp,'test',engine=engine())

    def test_backward_utc_jump_is_reported_before_model(self):
        cap=FixtureCapture(fault='mtu')
        instants=iter([datetime(2026,11,28,tzinfo=timezone.utc),datetime(2026,11,27,tzinfo=timezone.utc)])
        cap.wall_clock=lambda:next(instants)
        model=FixtureModel()
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(CaptureError,'clock_changed'):
            run_engine(DiagnosisEngine(capture=cap,model=model),tmp)
        self.assertEqual(model.calls,[])

    def test_response_grammar_forbids_execution_flags(self):
        eng=engine();original=eng.model.generate
        def generate(payload):
            value=original(payload);draft=json.loads(value['response']);draft.append(True);value['response']=json.dumps(draft);return value
        eng.model.generate=generate
        with tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):run_engine(eng,tmp)

    def test_model_receives_structured_current_measurements(self):
        eng=engine()
        with tempfile.TemporaryDirectory() as tmp:run_engine(eng,tmp)
        prompt=eng.model.calls[0]['prompt']
        body=prompt.split('<|start_header_id|>user<|end_header_id|>\n\n',1)[1].split('<|eot_id|>',1)[0]
        content=json.loads(body)['evidence'][0]['content']
        self.assertEqual(eng.model.calls[0]['format']['type'],'array')
        self.assertIsInstance(content,dict)
        self.assertEqual(content['expected_mtu'],1500)
        self.assertEqual(content['endpoints'][0]['observed']['mtu'],1400)

    def test_vtysh_proposal_requires_explicit_configuration_mode(self):
        eng=engine();original=eng.model.generate
        def generate(payload):
            raw=original(payload);value=json.loads(raw['response'])
            value[5]=[['r1','vtysh',['interface eth1','mtu 1500']]]
            raw['response']=json.dumps(value);return raw
        eng.model.generate=generate
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(DiagnosisError,'configuration_mode_required'):
            run_engine(eng,tmp)

    def test_compact_abstention_is_projected_without_inventing_diagnosis(self):
        from .agent import decision_to_draft
        value=dict(root_cause_class=None,root_cause_router=None,confidence=0,
                   explanation='Healthy baseline',evidence_ids=[],commands=[])
        draft=decision_to_draft(value)
        self.assertEqual(draft['status'],'abstain');self.assertIsNone(draft['confidence'])
        value['confidence']=.5
        with self.assertRaises(DiagnosisError):decision_to_draft(value)

    def test_array_transport_preserves_every_semantic_field_and_command(self):
        from .agent import decode_model_array,decision_to_draft
        args=['link','set','dev','eth1','mtu','1500']
        value=['mtu_mismatch','r1',.8,'Observed MTU differs from baseline',['e1'],[['r1','ip',args]]]
        named=decode_model_array(value)
        self.assertEqual(named,dict(root_cause_class='mtu_mismatch',root_cause_router='r1',confidence=.8,
            explanation=value[3],evidence_ids=['e1'],commands=[dict(router='r1',interpreter='ip',args=args)]))
        draft=decision_to_draft(named)
        self.assertEqual(draft['claims'][0]['evidence_ids'],['e1'])
        self.assertEqual(draft['proposed_patch'][0]['arguments'],['ip',*args])
        self.assertEqual(draft['proposed_patch'][0]['validation_status'],'unvalidated')

    def test_array_transport_rejects_shifted_fields_extra_values_and_type_coercion(self):
        from .agent import decode_model_array
        value=['mtu_mismatch','r1',.8,'Observed deviation',['e1'],[]]
        invalid=[value+[True],value[:-1],['r1','mtu_mismatch',.8,'text',['e1'],[]],
                 ['mtu_mismatch','r1','0.8','text',['e1'],[]],
                 ['mtu_mismatch','r1',.8,'text','e1',[]],
                 ['mtu_mismatch','r1',.8,'text',['e1'],[['r1','ip',['link'],True]]]]
        for case in invalid:
            with self.subTest(case=case),self.assertRaises(ValueError):decode_model_array(case)

    def test_model_grammar_allows_only_available_evidence_identifiers(self):
        import jsonschema
        from .agent import generation_schema
        value=['mtu_mismatch','r1',.8,'Observed deviation',['e1'],[]]
        schema=generation_schema(True,['e1','e2'])
        jsonschema.validate(value,schema)
        value[4]=['invented']
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,schema)
        with self.assertRaises(ValueError):generation_schema(True,[])

    def test_tool_grammar_requires_vtysh_lines_and_kernel_argv(self):
        import jsonschema
        from .agent import generation_schema
        value=['bgp_neighbor_shutdown','r1',.8,'Observed shutdown',['e1'],[['r1','vtysh',
            ['configure terminal','router bgp 65001','no neighbor 10.255.0.4 shutdown']]]]
        jsonschema.validate(value,generation_schema())
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,generation_schema(True))
        value[5][0][2]=['neighbor','10.255.0.4','shutdown']
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,generation_schema())

class LiveHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.engine=engine()
        artifacts=Path(self.tmp.name)/'synthetic-readiness'
        (artifacts/'private/knowledge/chroma').mkdir(parents=True)
        (artifacts/'host1/knowledge').mkdir(parents=True)
        (artifacts/'host1/knowledge/chunks.jsonl').write_text('')
        # Presence checks must use synthetic artifacts, never the operator's live database.
        self.root_patch=patch('live_api.server.ROOT',artifacts);self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.service=LiveService(self.tmp.name,'synthetic-test-token',engine=self.engine,baseline_confirmed=True,exclusive_model_session=True,replay_probe=lambda:False)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.service))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.service.close();self.tmp.cleanup()
    def call(self,path,body=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body else None,
            headers={'Authorization':'Bearer synthetic-test-token','Content-Type':'application/json'})
        try:r=self.opener.open(req,timeout=3)
        except urllib.error.HTTPError as exc:r=exc
        with r:return r.status,json.load(r),dict(r.headers)
    def finish(self,job):
        until=time.monotonic()+3
        while time.monotonic()<until:
            _,job,_=self.call('/v1/diagnoses/'+job['job_id'])
            if job['state'] in ('completed','failed','interrupted'):return job
            time.sleep(.01)
        self.fail('Job did not finish')
    def test_end_to_end_frozen_evidence_and_idempotency(self):
        req=request();req['variant']='zero_shot'
        status,job,headers=self.call('/v1/diagnoses',req);self.assertEqual(status,202)
        self.assertEqual(headers['X-Live-API-Simulation'],'false')
        job=self.finish(job);self.assertEqual(job['state'],'completed');Job.model_validate(job)
        for ev in job['evidence']:
            status,payload,_=self.call(ev['url']);self.assertEqual(status,200)
            self.assertEqual(payload['source_sha256'],ev['source_sha256']);self.assertNotIn('file',payload)
        status,duplicate,_=self.call('/v1/diagnoses',req);self.assertEqual(status,200)
        self.assertEqual(job['job_id'],duplicate['job_id']);self.assertEqual(len(self.engine.model.calls),1)
        index=Path(self.tmp.name)/job['job_id']/'facts.json';index.write_text('{}')
        self.assertEqual(self.call(job['evidence'][0]['url'])[0],409)

    def test_replay_listener_and_no_reservation_block_admission(self):
        for reserve,probe in ((False,False),(True,True)):
            self.service.exclusive_model_session=reserve;self.service.replay_probe=lambda:probe
            status,value,_=self.call('/v1/diagnoses',request())
            self.assertEqual(status,503);self.assertEqual(value['error']['code'],'replay_session_reserved' if probe else 'live_not_ready')
        self.assertEqual(self.engine.model.calls,[])

    def test_unconfirmed_baseline_is_not_ready(self):
        self.service.baseline_confirmed=False
        self.assertFalse(self.call('/health')[1]['ready'])
        self.assertEqual(self.call('/v1/diagnoses',request())[0],503)

    def test_changed_container_identity_invalidates_baseline(self):
        self.engine.capture.generation=1
        health=self.call('/health')[1]
        self.assertFalse(health['ready']);self.assertIn('baseline_runtime_changed',health['reasons'])
        self.assertEqual(self.call('/v1/diagnoses',request())[0],503)

    def test_backend_timeout_persists_hold_and_prevents_new_inference(self):
        self.engine.model.error=BackendUncertain('mock timeout')
        req=request();req['variant']='zero_shot'
        _,job,_=self.call('/v1/diagnoses',req);job=self.finish(job)
        self.assertEqual(job['state'],'failed');self.assertTrue(self.service.backend_held.exists())
        self.assertFalse(self.call('/health')[1]['ready'])
        req['request_id']=str(uuid.uuid4());self.assertEqual(self.call('/v1/diagnoses',req)[0],503)

if __name__=='__main__':unittest.main()
