"""Loopback-only synthetic server. Never imports Docker, collector or Ollama code."""
import argparse
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
from pydantic import ValidationError
from .examples import SOURCE, evidence, pending, terminal
from .models import VERSION, DiagnosisRequest, Job, Health, Capabilities, canonical, digest

TERMINAL = {'completed','failed','interrupted'}
UUID_RE = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

def utc():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

class ApiError(Exception):
    def __init__(self, status, code, retryable=False):
        self.status, self.code, self.retryable = status, code, retryable

class Service:
    simulation = True

    def _new_pending(self, req, jid):
        return pending(req, jid, utc())

    def _initial_source(self):
        return canonical(SOURCE).decode()

    def _check_readiness(self):
        if not self.ready or self.stop.is_set():
            raise ApiError(503, 'live_not_ready', True)

    def __init__(self, output, token, outcome='hypothesis', delay=1.0, deadline=600.0,
                 ready=True, variants=('zero_shot','text_rag','graph_rag'), clock=time.time):
        if not token or any(c.isspace() for c in token):
            raise ValueError('Set a nonempty whitespace-free LIVE_API_TOKEN')
        if outcome not in ('hypothesis','abstain','failed','interrupted'):
            raise ValueError('Invalid mock outcome')
        if not math.isfinite(delay) or delay<0 or not math.isfinite(deadline) or deadline<=0:
            raise ValueError('Invalid delay/deadline')
        if not set(variants) <= {'zero_shot','text_rag','graph_rag'}:
            raise ValueError('Invalid variants')
        self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True)
        self.token=token;self.outcome=outcome;self.delay=delay;self.deadline=deadline
        self.ready=ready;self.variants=list(variants);self.clock=clock
        self.lock=threading.RLock();self.stop=threading.Event();self.active=None;self.workers=[]
        self.owner=(self.output/'mock.lock').open('a+b')
        try:
            if os.name=='nt':
                import msvcrt
                self.owner.seek(0);self.owner.write(b'0');self.owner.flush();self.owner.seek(0)
                msvcrt.locking(self.owner.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.owner.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.owner.close()
            raise ValueError('Output directory already owned by another mock process') from None
        try:
            self.db=sqlite3.connect(self.output/'jobs.sqlite3',check_same_thread=False)
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, request TEXT NOT NULL, response TEXT NOT NULL, source TEXT NOT NULL, expires REAL)')
            with self.db:
                for jid,raw in self.db.execute('SELECT job_id,response FROM jobs').fetchall():
                    value=Job.model_validate_json(raw).model_dump()
                    if value['simulation'] is not self.simulation:
                        raise ValueError('Output contains jobs from a different service mode')
                    if value['state'] not in TERMINAL:
                        value.update(state='interrupted',updated_at=utc(),error=dict(
                            code='mock_restart' if self.simulation else 'live_restart',
                            message='Service restarted; job not resumed.',retryable=False))
                        self.db.execute('UPDATE jobs SET response=?,expires=? WHERE job_id=?',
                                        (canonical(value).decode(),self.clock()+604800,jid))
        except Exception:
            if hasattr(self,'db'):self.db.close()
            self.owner.close()
            raise

    def health(self):
        with self.lock:
            return Health.model_validate(dict(status='ok',mode='mock_live',simulation=True,active=self.active is not None,
                        ready=self.ready and not self.stop.is_set(),execution_allowed=False)).model_dump()

    def capabilities(self):
        return Capabilities.model_validate(dict(contract_version=VERSION,mode='mock_live',simulation=True,lab='rca',
                    variants=self.variants,real_variants_available=[],model_profile='not_used',
                    model_digest='0'*64,inventory_sha256=digest({'inventory':'synthetic'}),
                    max_body_bytes=4096,client_timeout_seconds=180,poll_seconds=1,
                    server_deadline_seconds=self.deadline,retention_seconds=604800,
                    freshness_policy=dict(max_age_seconds=15,max_skew_seconds=5,clock='host1'),
                    readiness=dict(mock=self.ready,collector=False,model=False,linter=False,executor=False),
                    note='Synthetic contract simulator; do not inject faults based on mock readiness.')).model_dump()

    def _row(self, field, value):
        # field comes only from the two internal callers, never HTTP input.
        row=self.db.execute(f'SELECT job_id,request,response,source,expires FROM jobs WHERE {field}=?',(value,)).fetchone()
        if row is None:raise ApiError(404,'not_found')
        if row[4] is not None and self.clock()>=row[4]:raise ApiError(410,'run_expired')
        return row

    def get(self, value, by_request=False):
        with self.lock:
            return json.loads(self._row('request_id' if by_request else 'job_id',value)[2])

    def submit(self, req):
        payload=canonical(req).decode()
        with self.lock:
            try:
                row=self._row('request_id',req['request_id'])
            except ApiError as exc:
                if exc.status!=404:raise
            else:
                if row[1]!=payload:raise ApiError(409,'request_id_conflict')
                response=json.loads(row[2])
                return (200 if response['state'] in TERMINAL else 202),response
            if req['variant'] not in self.variants:raise ApiError(422,'unsupported_variant')
            if self.active is not None:raise ApiError(503,'agent_busy',True)
            self._check_readiness()
            jid=str(uuid.uuid4());value=self._new_pending(req,jid);Job.model_validate(value)
            with self.db:
                self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,NULL)',
                    (jid,req['request_id'],payload,canonical(value).decode(),self._initial_source()))
            self.active=jid
            worker=threading.Thread(target=self._work,args=(jid,),daemon=True)
            self.workers.append(worker)
            try:worker.start()
            except Exception:
                self._finish(jid,'failed',0.0)
                raise
            return 202,value

    def _save(self, jid, value, expires=None):
        Job.model_validate(value)
        with self.db:
            self.db.execute('UPDATE jobs SET response=?,expires=? WHERE job_id=?',
                            (canonical(value).decode(),expires,jid))

    def _stage(self,jid,state):
        with self.lock:
            value=json.loads(self._row('job_id',jid)[2]);value.update(state=state,updated_at=utc())
            self._save(jid,value)

    def _finish(self,jid,outcome,elapsed,deadline=False):
        with self.lock:
            value=json.loads(self._row('job_id',jid)[2]);value['updated_at']=utc()
            value=terminal(value,outcome,elapsed)
            if deadline:value['error']=dict(code='mock_deadline',message='Synthetic job deadline exceeded.',retryable=False)
            self._save(jid,value,self.clock()+604800);self.active=None

    def _work(self,jid):
        start=time.monotonic()
        try:
            self._stage(jid,'collecting')
            interrupted=self.stop.wait(min(self.delay/2,self.deadline))
            if not interrupted and time.monotonic()-start<self.deadline:
                self._stage(jid,'reasoning')
                interrupted=self.stop.wait(min(self.delay/2,max(0,self.deadline-(time.monotonic()-start))))
            elapsed=time.monotonic()-start
            exceeded=elapsed>=self.deadline
            self._finish(jid,'interrupted' if interrupted else 'failed' if exceeded else self.outcome,
                         elapsed,deadline=exceeded and not interrupted)
        except Exception:
            # Fail closed if storage/validation fails. Keep active if even terminal persistence fails.
            try:self._finish(jid,'failed',time.monotonic()-start)
            except Exception:pass

    def get_evidence(self,jid,eid):
        with self.lock:
            row=self._row('job_id',jid);job=json.loads(row[2])
            if job['state']!='completed' or eid!='e1':raise ApiError(404,'not_found')
            expected=job['evidence'][0]
            try:source=json.loads(row[3])
            except ValueError:raise ApiError(409,'evidence_changed') from None
            if digest(source)!=expected['source_sha256']:raise ApiError(409,'evidence_changed')
            ev=evidence()
            if ev['source_sha256']!=expected['source_sha256']:raise ApiError(409,'evidence_changed')
            return ev

    def close(self):
        self.stop.set()
        for w in self.workers:w.join(timeout=5)
        if any(w.is_alive() for w in self.workers):raise RuntimeError('Mock worker did not stop')
        self.db.close();self.owner.close()


def strict_json(raw):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('duplicate key')
            result[k]=v
        return result
    def bad(value):raise ValueError('nonfinite number')
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=bad)


def handler(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass  # Do not log tokens or request bodies.

        def send_json(self,status,value,headers=None):
            body=canonical(value)
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('Connection','close')
            self.send_header('X-Live-API-Simulation','true' if service.simulation else 'false')
            for k,v in (headers or {}).items():self.send_header(k,v)
            self.end_headers();self.close_connection=True
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass

        def handle_request(self):
            request_id=None
            try:
                auth=self.headers.get_all('Authorization',[])
                if len(auth)!=1 or not hmac.compare_digest(auth[0].encode(),('Bearer '+service.token).encode()):
                    raise ApiError(401,'unauthorized')
                path=self.path
                if '?' in path or '%' in path or '..' in path or not path.startswith('/'):
                    raise ApiError(404,'not_found')
                known=path in ('/health','/v1/capabilities','/v1/diagnoses') or bool(re.fullmatch(r'/v1/diagnoses/(?:by-request/)?'+UUID_RE+r'(?:/evidence/e[0-9]+)?',path))
                if not known:raise ApiError(404,'not_found')
                expected='POST' if path=='/v1/diagnoses' else 'GET'
                if self.command!=expected:raise ApiError(405,'method_not_allowed')
                if expected=='POST':
                    if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Encoding'):
                        raise ApiError(400,'invalid_request')
                    lengths=self.headers.get_all('Content-Length',[])
                    if len(lengths)!=1 or not lengths[0].isdigit():raise ApiError(400,'invalid_request')
                    length=int(lengths[0])
                    if length>4096:raise ApiError(413,'body_too_large')
                    if self.headers.get_content_type()!='application/json':raise ApiError(415,'unsupported_media_type')
                    self.connection.settimeout(5)
                    raw=self.rfile.read(length)
                    if len(raw)!=length:raise ApiError(400,'invalid_request')
                    try:
                        body=strict_json(raw)
                        if isinstance(body,dict):
                            if body.get('contract_version') not in (None,VERSION):raise ApiError(422,'unsupported_contract')
                            if body.get('variant') not in (None,'zero_shot','text_rag','graph_rag'):raise ApiError(422,'unsupported_variant')
                        req=DiagnosisRequest.model_validate(body).model_dump()
                    except (ValueError,TypeError,ValidationError):raise ApiError(400,'invalid_request') from None
                    request_id=req['request_id']
                    status,value=service.submit(req)
                    return self.send_json(status,value,{'Location':f"/v1/diagnoses/{value['job_id']}",**({'Retry-After':'1'} if status==202 else {})})
                if path=='/health':return self.send_json(200,service.health())
                if path=='/v1/capabilities':return self.send_json(200,service.capabilities())
                parts=path.split('/')
                if len(parts)==5 and parts[3]=='by-request':value=service.get(parts[4],True)
                elif len(parts)==6 and parts[4]=='evidence':value=service.get_evidence(parts[3],parts[5])
                elif len(parts)==4:value=service.get(parts[3])
                else:raise ApiError(404,'not_found')
                return self.send_json(200,value)
            except ApiError as exc:
                return self.send_json(exc.status,dict(contract_version=VERSION,request_id=request_id,
                    error=dict(code=exc.code,message=exc.code.replace('_',' '),retryable=exc.retryable)),
                    {'Retry-After':'1'} if exc.status==503 else {})
            except Exception:
                return self.send_json(500,dict(contract_version=VERSION,request_id=request_id,
                    error=dict(code='internal_error',message='Mock internal error.',retryable=False)))

        do_GET=do_POST=do_PUT=do_DELETE=do_PATCH=do_HEAD=do_OPTIONS=handle_request
    return Handler


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',type=int,default=8766)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--outcome',choices=['hypothesis','abstain','failed','interrupted'],default='hypothesis')
    ap.add_argument('--delay',type=float,default=1.0)
    ap.add_argument('--deadline',type=float,default=600.0)
    ap.add_argument('--not-ready',action='store_true')
    ap.add_argument('--variants',nargs='+',choices=['zero_shot','text_rag','graph_rag'],default=['zero_shot','text_rag','graph_rag'])
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[2]
    if not args.output.resolve().is_relative_to(root/'private'):
        ap.error('--output must be inside private/ (ignored local state)')
    if args.port in (8765,11434) or not 0<=args.port<=65535:
        ap.error('Use a separate mock port, never replay/Ollama ports')
    service=None;server=None
    try:
        service=Service(args.output,os.environ.get('LIVE_API_TOKEN',''),args.outcome,args.delay,
                        args.deadline,not args.not_ready,args.variants)
        server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(service))
        print(json.dumps(dict(mode='mock_live',simulation=True,host='127.0.0.1',port=server.server_port)),flush=True)
        server.serve_forever()
    except KeyboardInterrupt:pass
    except (OSError,ValueError):ap.exit(2,'Mock could not start; check token, port and private output ownership.\n')
    finally:
        if server:server.server_close()
        if service:service.close()

if __name__=='__main__':main()
