"""Offline contracts and ephemeral localhost HTTP; no real model or router."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import sqlite3
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid
from pydantic import ValidationError
from .examples import examples, request, schema
from .models import (DiagnosisRequest, Job, EvidencePayload, ErrorResponse,
                     LintInput, LintOutput, validate_lint_pair, digest)
from .mock import ApiError, Service, handler

class ContractTests(unittest.TestCase):
    def test_exported_artifacts_match_sources_and_examples_validate(self):
        here=Path(__file__).resolve().parent
        self.assertEqual(json.loads((here/'schema.json').read_text()),schema())
        self.assertEqual(json.loads((here/'examples.json').read_text()),examples())
        e=examples();DiagnosisRequest.model_validate(e['request'])
        for key in ('pending','hypothesis','abstain','failed','interrupted'):
            Job.model_validate(e[key])
        EvidencePayload.model_validate(e['evidence']);ErrorResponse.model_validate(e['error'])
        validate_lint_pair(e['lint_input'],e['lint_output'])

    def test_json_schema_validates_examples_and_rejects_bad_shape(self):
        from jsonschema import Draft202012Validator
        bundle=schema();Draft202012Validator.check_schema(bundle)
        e=examples()
        mapping={'request':'DiagnosisRequest','pending':'Job','hypothesis':'Job','abstain':'Job',
                 'failed':'Job','interrupted':'Job','evidence':'EvidencePayload',
                 'lint_input':'LintInput','lint_output':'LintOutput','error':'ErrorResponse'}
        for key,name in mapping.items():
            validator=Draft202012Validator({**bundle, '$ref':'#/$defs/'+name})
            validator.validate(e[key])
            changed={**e[key],'unexpected':'forbidden'}
            self.assertFalse(validator.is_valid(changed),key)
        invalid={**e['request'],'execution_allowed':True}
        self.assertFalse(Draft202012Validator({**bundle,'$ref':'#/$defs/DiagnosisRequest'}).is_valid(invalid))

    def test_reject_ground_truth_paths_missing_fields_bad_uuid_date_and_execution(self):
        for key,value in [('ground_truth',{}),('fault_id','F01'),('path','/tmp/a'),
                          ('execution_allowed',True),('execution_allowed',0),('request_id','../bad'),
                          ('symptom_detected_at_utc','2026-11-21T00:00:00'),
                          ('symptom_detected_at_utc','2026-02-31T00:00:00Z')]:
            r=request();r[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValidationError):
                DiagnosisRequest.model_validate(r)
        for key in request():
            r=request();del r[key]
            with self.assertRaises(ValidationError):DiagnosisRequest.model_validate(r)

    def test_reject_foreign_refs_commands_confidence_and_provenance(self):
        e=examples()['hypothesis']
        for edit in [lambda v:v['result']['claims'][0].update(evidence_ids=['foreign']),
                     lambda v:v['assessment'].update(confidence=0.9),
                     lambda v:v['assessment']['commands'][0]['args'].append('bad'),
                     lambda v:v['evidence'][0].update(url='/private/key'),
                     lambda v:v['provenance'].update(actual_variant='zero_shot'),
                     lambda v:v['timing'].update(total_seconds=float('nan')),
                     lambda v:v['assessment'].update(confidence=float('inf'))]:
            value=deepcopy(e);edit(value)
            with self.assertRaises(ValidationError):Job.model_validate(value)

    def test_abstain_and_terminal_states_do_not_mix(self):
        e=examples()['abstain'];e['assessment']['router']='r1'
        with self.assertRaises(ValidationError):Job.model_validate(e)
        f=examples()['failed'];f['result']=examples()['abstain']['result']
        with self.assertRaises(ValidationError):Job.model_validate(f)

    def test_lint_hash_binding_and_violation_indices(self):
        e=examples();a=e['lint_input'];b=e['lint_output']
        a['commands'][0]['args'][-1]='1400'
        with self.assertRaises(ValidationError):LintInput.model_validate(a)
        e=examples();e['lint_output']['job_id']=str(uuid.uuid4())
        with self.assertRaises(ValueError):validate_lint_pair(e['lint_input'],e['lint_output'])
        e=examples();e['lint_output'].update(status='rejected',violations=[dict(command_index=99,code='bad',message='bad')])
        with self.assertRaises(ValueError):validate_lint_pair(e['lint_input'],e['lint_output'])
        self.assertEqual(digest({'b':2,'a':1}),digest({'a':1,'b':2}))

    def test_shell_payload_is_not_a_wire_command_or_linter_approval(self):
        e=examples();e['lint_input']['commands'][0]['args']=['link','set','eth1; reboot']
        e['lint_input']['commands_sha256']=digest(e['lint_input']['commands'])
        with self.assertRaises(ValidationError):LintInput.model_validate(e['lint_input'])
        e=examples();e['lint_output']['violations']=[dict(command_index=0,code='bad',message='bad')]
        with self.assertRaises(ValidationError):LintOutput.model_validate(e['lint_output'])

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.service=Service(self.tmp.name,'synthetic-test-token',delay=0.25)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.service))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.service.close();self.tmp.cleanup()

    def call(self,path,body=None,method=None,raw=None,headers=None):
        data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        hs={'Authorization':'Bearer synthetic-test-token','Content-Type':'application/json'}
        hs.update(headers or {})
        req=urllib.request.Request(self.url+path,data=data,method=method,headers=hs)
        try:r=self.opener.open(req,timeout=3)
        except urllib.error.HTTPError as exc:r=exc
        with r:return r.status,json.load(r),dict(r.headers)

    def submit(self):
        r=request();r['request_id']=str(uuid.uuid4());return r,self.call('/v1/diagnoses',r)

    def done(self,jid):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            s,v,h=self.call('/v1/diagnoses/'+jid)
            if v['state'] in ('completed','failed','interrupted'):return v
            time.sleep(.01)
        self.fail('Mock job did not finish')

    def test_auth_health_and_capabilities_mark_mock(self):
        s,v,h=self.call('/health');self.assertEqual(s,200);self.assertTrue(v['simulation']);self.assertFalse(v['active'])
        self.assertEqual(h['Cache-Control'],'no-store')
        s,v,h=self.call('/v1/capabilities');self.assertEqual(v['real_variants_available'],[])
        self.assertFalse(v['readiness']['model']);self.assertFalse(v['readiness']['collector'])
        for path in ('/health','/v1/capabilities','/v1/diagnoses/'+str(uuid.uuid4())):
            self.assertEqual(self.call(path,headers={'Authorization':'Bearer wrong'})[0],401)
        self.assertEqual(self.call('/v1/diagnoses',request(),headers={'Authorization':'Bearer wrong'})[0],401)

    def test_completed_evidence_and_no_external_execution(self):
        with patch('subprocess.run',side_effect=AssertionError('No process calls allowed')):
            r,(s,v,h)=self.submit();self.assertEqual(s,202);self.assertTrue(v['simulation'])
            self.assertEqual(h['Location'],'/v1/diagnoses/'+v['job_id'])
            job=self.done(v['job_id']);Job.model_validate(job)
        self.assertEqual(job['result']['status'],'hypothesis');self.assertFalse(job['execution_allowed'])
        e=job['evidence'][0];s,ev,_=self.call(e['url']);self.assertEqual(s,200)
        self.assertEqual(ev['source_sha256'],digest(json.loads(ev['content'])))
        self.assertNotIn('source_path',ev)

    def test_lookup_canonical_idempotency_and_conflict(self):
        r,(s,v,h)=self.submit();s,other,_=self.call('/v1/diagnoses',dict(reversed(list(r.items()))))
        self.assertEqual(s,202);self.assertEqual(other['job_id'],v['job_id'])
        s,found,_=self.call('/v1/diagnoses/by-request/'+r['request_id']);self.assertEqual(found['job_id'],v['job_id'])
        changed={**r,'variant':'text_rag'};self.assertEqual(self.call('/v1/diagnoses',changed)[0],409)
        self.done(v['job_id']);self.assertEqual(self.call('/v1/diagnoses',r)[0],200)
        self.assertEqual(self.service.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],1)

    def test_concurrent_duplicate_and_busy_admission(self):
        r=request();r['request_id']=str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses=list(pool.map(lambda _:self.call('/v1/diagnoses',r),range(6)))
        self.assertEqual({x[0] for x in responses},{202})
        self.assertEqual(len({x[1]['job_id'] for x in responses}),1)
        new={**r,'request_id':str(uuid.uuid4())}
        s,v,h=self.call('/v1/diagnoses',new);self.assertEqual(s,503)
        self.assertEqual(v['error']['code'],'agent_busy');self.assertEqual(h['Retry-After'],'1')
        self.assertEqual(self.call('/v1/diagnoses/by-request/'+new['request_id'])[0],404)
        self.assertTrue(self.call('/health')[1]['active'])

    def test_abstain_failed_and_interrupted_are_distinct(self):
        for outcome in ('abstain','failed','interrupted'):
            self.service.outcome=outcome
            r,(_,v,_)=self.submit();job=self.done(v['job_id']);Job.model_validate(job)
            if outcome=='abstain':
                self.assertEqual(job['state'],'completed');self.assertEqual(job['result']['status'],'abstain')
                self.assertEqual(job['assessment']['commands'],[])
            else:
                self.assertEqual(job['state'],outcome);self.assertNotIn('result',job)

    def test_client_abandonment_and_server_deadline(self):
        # Client stops polling before job finishes; GET by request resumes without a second POST.
        self.service.delay=.4
        r,(_,v,_)=self.submit();self.assertTrue(self.service.health()['active'])
        time.sleep(.03)
        self.assertEqual(self.call('/v1/diagnoses/by-request/'+r['request_id'])[1]['job_id'],v['job_id'])
        self.assertEqual(self.done(v['job_id'])['state'],'completed')
        self.service.deadline=.02
        r,(_,v,_)=self.submit();job=self.done(v['job_id'])
        self.assertEqual(job['state'],'failed');self.assertEqual(job['error']['code'],'mock_deadline')
        self.assertFalse(self.service.health()['active'])

    def test_lost_post_response_can_be_reconciled(self):
        r=request();r['request_id']=str(uuid.uuid4());body=json.dumps(r).encode()
        with socket.create_connection(('127.0.0.1',self.server.server_port),timeout=3) as sock:
            head=('POST /v1/diagnoses HTTP/1.1\r\nHost: localhost\r\n'
                  'Authorization: Bearer synthetic-test-token\r\nContent-Type: application/json\r\n'
                  f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode()
            sock.sendall(head+body)
            # Disconnect without ever consuming the acceptance/job ID response.
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            status,value,_=self.call('/v1/diagnoses/by-request/'+r['request_id'])
            if status==200:break
            time.sleep(.01)
        self.assertEqual(status,200)
        self.assertEqual(self.done(value['job_id'])['state'],'completed')
        self.assertEqual(self.service.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],1)

    def test_expiry_and_changed_evidence(self):
        r,(_,v,_)=self.submit();job=self.done(v['job_id'])
        with self.service.lock,self.service.db:
            self.service.db.execute('UPDATE jobs SET source=? WHERE job_id=?',('{"modified":true}',v['job_id']))
        self.assertEqual(self.call(job['evidence'][0]['url'])[0],409)
        self.service.clock=lambda:time.time()+604801
        for path in ('/v1/diagnoses/'+v['job_id'],'/v1/diagnoses/by-request/'+r['request_id'],job['evidence'][0]['url']):
            self.assertEqual(self.call(path)[0],410)
        self.assertEqual(self.call('/v1/diagnoses',r)[0],410)

    def test_invalid_json_encoding_extra_flags_and_methods(self):
        for raw in (b'{"request_id":"a","request_id":"b"}',b'NaN',b'\xff',b'{',b'[]'):
            self.assertEqual(self.call('/v1/diagnoses',raw=raw)[0],400)
        for field in ('ground_truth','fault_id','commands','evidence','source_path'):
            self.assertEqual(self.call('/v1/diagnoses',{**request(),field:'forbidden'})[0],400)
        self.assertEqual(self.call('/v1/diagnoses',{**request(),'execution_allowed':True})[0],400)
        self.assertEqual(self.call('/v1/diagnoses',request(),headers={'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.call('/v1/diagnoses',raw=b'x'*4097)[0],413)
        self.assertEqual(self.call('/health',method='POST',raw=b'{}')[0],405)
        self.assertEqual(self.call('/v1/diagnoses',method='GET')[0],405)
        for path in ('/private/key','/v1/diagnoses/../secret','/v1/diagnoses/%2e%2e','/health?x=1'):
            self.assertEqual(self.call(path)[0],404)

    def test_unsupported_version_variant_and_not_ready(self):
        for key,val in [('contract_version','live.v999'),('variant','invented')]:
            self.assertEqual(self.call('/v1/diagnoses',{**request(),key:val})[0],422)
        self.service.variants=['zero_shot']
        self.assertEqual(self.call('/v1/diagnoses',request())[0],422)
        self.service.ready=False
        s,v,h=self.call('/v1/diagnoses',{**request(),'variant':'zero_shot'})
        self.assertEqual(s,503);self.assertEqual(v['error']['code'],'live_not_ready')

class PersistenceTests(unittest.TestCase):
    def test_restart_keeps_completed_and_interrupts_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=Service(tmp,'test',delay=0)
            r=request();_,value=service.submit(r)
            for w in service.workers:w.join()
            completed=service.get(value['job_id']);service.close()
            # Simulate durable admission followed by process loss before a worker starts.
            from .examples import pending
            rid=str(uuid.uuid4());jid=str(uuid.uuid4());req={**r,'request_id':rid}
            db=sqlite3.connect(Path(tmp)/'jobs.sqlite3')
            with db:db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,NULL)',(jid,rid,json.dumps(req),json.dumps(pending(req,jid)), '{}'))
            db.close()
            service=Service(tmp,'test')
            try:
                self.assertEqual(service.get(value['job_id']),completed)
                self.assertEqual(service.get(rid,True)['state'],'interrupted')
                self.assertFalse(service.health()['active'])
                self.assertEqual(service.submit(r)[0],200)
            finally:service.close()

    def test_output_owner_and_bad_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kwargs in ({'token':''},{'token':'with space'},{'token':'a','delay':float('nan')}):
                with self.assertRaises(ValueError):Service(tmp,**kwargs)
            service=Service(tmp,'a')
            try:
                with self.assertRaises(ValueError):Service(tmp,'b')
            finally:service.close()

if __name__=='__main__':unittest.main()
