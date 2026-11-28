"""Read-only live API: separate loopback listener, real capture, no executor."""
import argparse
import importlib.util
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from .agent import DiagnosisEngine, DiagnosisError, BackendUncertain, PinnedOllama, replay_present
from .capture import ROOT, CaptureError
from .mock import Service, ApiError, handler, utc
from .models import VERSION, Job, LiveHealth, LiveCapabilities, EvidencePayload
from .capture import write

class LiveService(Service):
    simulation=False
    def __init__(self,output,token,engine=None,baseline_confirmed=False,
                 exclusive_model_session=False,replay_probe=None,deadline=600):
        self.engine=engine or DiagnosisEngine(model=PinnedOllama(),analyze_healthy=True)
        self.baseline_confirmed=baseline_confirmed
        self.exclusive_model_session=exclusive_model_session
        self.replay_probe=replay_probe or replay_present
        self.backend_held=Path(output)/'backend-completion-unknown'
        baseline_state=self.engine.capture.readiness()
        self.baseline_signature=(baseline_state.get('runtime_signature'),baseline_state['inventory_sha256'])
        super().__init__(output,token,deadline=deadline)

    def _new_pending(self,req,jid):
        stamp=utc()
        return dict(contract_version=VERSION,request_id=req['request_id'],job_id=jid,mode='live',lab='rca',
                    variant=req['variant'],state='accepted',received_at=stamp,updated_at=stamp,
                    execution_allowed=False,simulation=False)

    def _initial_source(self):return '{}'

    def readiness(self):
        capture=self.engine.capture.readiness();reasons=[]
        if not capture['ready']:reasons.append(capture['reason'])
        if not self.baseline_confirmed:reasons.append('baseline_not_confirmed')
        elif (capture.get('runtime_signature'),capture['inventory_sha256'])!=self.baseline_signature:
            reasons.append('baseline_runtime_changed')
        if not self.exclusive_model_session:reasons.append('model_session_not_reserved')
        if self.replay_probe():reasons.append('replay_session_reserved')
        if self.backend_held.exists() and self.active is None:reasons.append('model_completion_unknown')
        model=bool(self.engine.model and self.engine.model.ready()) if not reasons else False
        if not model and not reasons:reasons.append('model_unavailable_or_digest_mismatch')
        return not reasons,reasons,capture,model

    def _check_readiness(self):
        ready,reasons,_,_=self.readiness()
        if self.stop.is_set() or not ready:
            code='replay_session_reserved' if 'replay_session_reserved' in reasons else 'live_not_ready'
            raise ApiError(503,code,True)

    def health(self):
        with self.lock:
            ready,reasons,_,_=self.readiness()
            return LiveHealth(status='ok',mode='live',simulation=False,active=self.active is not None or self.backend_held.exists(),
                              ready=ready and not self.stop.is_set(),reasons=reasons,execution_allowed=False).model_dump()

    def capabilities(self):
        ready,reasons,capture,model=self.readiness()
        # These local artifacts are prerequisites, not a claim about retrieval quality.
        retrieval=(ROOT/'private/knowledge/chroma').is_dir() and (ROOT/'host1/knowledge/chunks.jsonl').is_file()
        graph=importlib.util.find_spec('networkx') is not None
        variants=['zero_shot']+(['text_rag'] if retrieval else [])+(['graph_rag'] if retrieval and graph else [])
        return LiveCapabilities(contract_version=VERSION,mode='live',simulation=False,lab='rca',
            variants=variants,real_variants_available=variants,model_profile=self.engine.profile['model'],
            model_digest=self.engine.profile['expected_digest'],inventory_sha256=capture['inventory_sha256'],
            max_body_bytes=4096,client_timeout_seconds=180,poll_seconds=1,server_deadline_seconds=self.deadline,retention_seconds=604800,
            freshness_policy=dict(max_age_seconds=15,max_skew_seconds=5,clock='host1'),
            readiness=dict(baseline=self.baseline_confirmed and 'baseline_runtime_changed' not in reasons,collector=capture['ready'],model=model,retrieval=retrieval,graph=graph,linter=False,executor=False),
            supported_causes=list(self.engine.supported_causes),execution_allowed=False,
            note='Diagnosis and unexecuted proposals for supported configuration deviations; execution requires separate authorized CLI. '+','.join(reasons)).model_dump()

    def submit(self,req):
        # Variants beyond zero-shot require actual retrieval artifacts on this host.
        # Idempotent lookup remains available even when readiness changes.
        with self.lock:
            exists=self.db.execute('SELECT 1 FROM jobs WHERE request_id=?',(req['request_id'],)).fetchone()
            if not exists and req['variant'] not in self.capabilities()['variants']:
                raise ApiError(422,'unsupported_variant')
            return super().submit(req)

    def _work(self,jid):
        start=time.monotonic()
        try:
            self._stage(jid,'collecting')
            with self.lock:
                row=self._row('job_id',jid);req=json.loads(row[1]);initial=json.loads(row[2])
            if self.replay_probe():raise DiagnosisError('replay_session_reserved')
            # Survives a killed process: a restart must not assume external inference stopped.
            self.backend_held.write_text('Job '+jid+' was in flight. Verify backend completion before clearing after an interrupted process.\n')
            value=self.engine.run(req,jid,self.output/jid,stage=lambda state:self._stage(jid,state),stop=self.stop)
            if self.stop.is_set():raise DiagnosisError('interrupted_after_model')
            if time.monotonic()-start>self.deadline:raise DiagnosisError('job_deadline_exceeded')
            value['received_at']=initial['received_at'];value['updated_at']=utc()
            write(self.output/jid/'response.json',value)
            with self.lock:
                self._save(jid,value,self.clock()+604800)
                self.backend_held.unlink(missing_ok=True);self.active=None
        except Exception as exc:
            if isinstance(exc,BackendUncertain):self.backend_held.write_text('Check model backend completion before clearing this private marker.\n')
            code=('model_completion_unknown' if isinstance(exc,BackendUncertain) else
                  str(exc) if isinstance(exc,(DiagnosisError,CaptureError)) else 'live_internal_error')
            # Keep diagnostics private; public errors carry controlled codes only.
            (self.output/(jid+'-error.txt')).write_text(type(exc).__name__+': '+str(exc),encoding='utf-8')
            with self.lock:
                value=json.loads(self._row('job_id',jid)[2])
                value.update(state='interrupted' if self.stop.is_set() else 'failed',updated_at=utc(),
                             error=dict(code=code,message='Read-only live diagnosis did not complete.',retryable=False))
                self._save(jid,value,self.clock()+604800)
                if not isinstance(exc,BackendUncertain):self.backend_held.unlink(missing_ok=True)
                self.active=None

    def get_evidence(self,jid,eid):
        with self.lock:
            row=self._row('job_id',jid);job=json.loads(row[2])
            if job['state']!='completed':raise ApiError(404,'not_found')
            index=self.output/jid/'evidence-index.json'
            try:
                refs=json.loads(index.read_text());ref=next((r for r in refs if r['payload']['id']==eid),None)
                if ref is None:raise ApiError(404,'not_found')
                manifest=next(e for e in job['evidence'] if e['id']==eid)
                if any(ref['payload'][k]!=manifest[k] for k in ('id','kind','source_id','source_sha256','locator')):raise ValueError('binding')
                self.engine._verify_sources(self.output/jid,[ref])
                payload=EvidencePayload.model_validate(ref['payload']).model_dump()
                # Verify exact fragment at the JSON pointer; index is not a trusted replacement for source bytes.
                source=json.loads((self.output/jid/ref['file']).read_bytes())
                for token in ref['payload']['locator'].split('/')[1:]:
                    if not token:continue
                    token=token.replace('~1','/').replace('~0','~')
                    source=source[int(token)] if isinstance(source,list) else source[token]
                from .models import canonical
                if canonical(source).decode()!=payload['content']:raise ValueError('fragment')
                return payload
            except ApiError:raise
            except (OSError,ValueError,KeyError,StopIteration):raise ApiError(409,'evidence_changed') from None

    def close(self):
        # Collector/model calls are bounded but must really return before storage/lock is released.
        self.stop.set()
        for worker in self.workers:
            while worker.is_alive():worker.join(.5)
        self.db.close();self.owner.close()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--port',type=int,default=8766)
    ap.add_argument('--exclusive-model-session',action='store_true',help='Operator reserves Ollama for live; any replay listener still blocks inference')
    args=ap.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'private'):ap.error('Output must be inside private/')
    if args.port in (8765,11434) or not 0<=args.port<=65535:ap.error('Separate loopback port required')
    service=None;server=None
    try:
        engine=DiagnosisEngine(model=PinnedOllama(),analyze_healthy=True);baseline=False
        args.output.mkdir(parents=True,exist_ok=True)
        if engine.capture.readiness()['ready']:
            p=subprocess.run([sys.executable,str(ROOT/'lab/host1/frr/verify-runtime.py'),str(args.output/'baseline')],capture_output=True,text=True,timeout=120)
            (args.output/'baseline-check.log').write_text(p.stdout+p.stderr)
            baseline=p.returncode==0
        service=LiveService(args.output,os.environ.get('LIVE_API_TOKEN',''),engine=engine,
                            baseline_confirmed=baseline,exclusive_model_session=args.exclusive_model_session)
        server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(service))
        print(json.dumps(dict(mode='live',simulation=False,host='127.0.0.1',port=server.server_port,health=service.health())),flush=True)
        server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        if server:server.server_close()
        if service:service.close()

if __name__=='__main__':main()
