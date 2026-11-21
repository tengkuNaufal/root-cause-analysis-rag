"""Local-only, synchronous replay API. No shell, uploads, live collection or executor."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
import time
import uuid
from urllib.parse import urlsplit
from agent_contract.models import Request, Response, validate_pair
from knowledge.evidence import ROOT, local_path, read, verify, ref
from reasoning_agent import temporal, mtu

CATALOG=ROOT/'host1/reasoning_agent/replay-scenarios.json'
MAX_BODY=4096

class ApiError(Exception):
    def __init__(self,status,code):self.status=status;self.code=code

def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate_json_key')
        result[key]=value
    return result

class ReplayService:
    def __init__(self,output,catalog=CATALOG,transport=None):
        self.output=local_path(output);self.output.mkdir(parents=True,exist_ok=False)
        self.transport=transport;self.lock=threading.Lock();self.records={};self.catalog_ref=ref(catalog)
        document=read(local_path(catalog));self.scenarios={}
        if document.get('schema_version')!='replay-catalog-1.0':raise ValueError('Invalid replay catalog')
        for entry in document['scenarios']:
            if (set(entry)!={'id','profile','input','synthetic','description'} or
                not re.fullmatch(r'[a-z0-9._-]{1,80}',entry['id']) or entry['id'] in self.scenarios or
                entry['profile'] not in ('temporal-bound','mtu-observation') or type(entry['synthetic']) is not bool):
                raise ValueError('Invalid or duplicate scenario')
            verify(entry['input']['path'],entry['input']['sha256']);self.scenarios[entry['id']]=entry
        self.persist('service.json',dict(api_version='1.0',catalog=self.catalog_ref,
            started_at=datetime.now(timezone.utc).isoformat(),bind='127.0.0.1',mode='replay_only',execution_allowed=False))

    def persist(self,name,value):
        (self.output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

    def catalog(self):
        return dict(api_version='1.0',mode='replay_only',scenarios=[{k:e[k] for k in ('id','profile','synthetic','description')}
            for e in self.scenarios.values()],execution_allowed=False)

    def get_record(self,run_id):
        if not re.fullmatch(r'[0-9a-f]{32}',run_id) or run_id not in self.records:raise ApiError(404,'run_not_found')
        return self.records[run_id]

    def evidence(self,run_id,evidence_id):
        record=self.get_record(run_id)
        private=record['sources'].get(evidence_id)
        if private is None:raise ApiError(404,'evidence_not_found')
        try:verify(private['path'],private['sha256'])
        except (ValueError,OSError):raise ApiError(409,'evidence_source_changed')
        return next(e for e in record['public']['evidence'] if e['id']==evidence_id)

    def replay(self,scenario_id):
        if scenario_id not in self.scenarios:raise ApiError(404,'scenario_not_found')
        if not self.lock.acquire(blocking=False):raise ApiError(503,'agent_busy')
        started=time.perf_counter();run_id=uuid.uuid4().hex;folder=self.output/run_id
        entry=self.scenarios[scenario_id]
        try:
            folder.mkdir()
            try:
                verify(self.catalog_ref['path'],self.catalog_ref['sha256'])
                source=verify(entry['input']['path'],entry['input']['sha256'])
            except (ValueError,OSError):raise ApiError(409,'registered_source_changed')
            work=folder/'agent';agent_started=time.perf_counter()
            if entry['profile']=='temporal-bound':
                audit=temporal.run(source,work,mode='replay',extractor='bound',transport=self.transport)
            else:audit=mtu.run(source,work,mode='replay',transport=self.transport)
            agent_seconds=time.perf_counter()-agent_started
            result=Response.model_validate(read(work/'output-contract.json')).model_dump()
            if result['execution_allowed'] is not False or result['proposed_patch']:
                raise ApiError(500,'execution_contract_violation')
            request_path=work/'input-contract.json';selected=[]
            if request_path.exists():
                req=Request.model_validate(read(request_path));validate_pair(req.model_dump(),result);selected=req.evidence
            elif result['status']!='abstain':raise ApiError(500,'missing_input_contract')
            if result['status']=='hypothesis' and not audit.get('contract_valid'):raise ApiError(500,'unvalidated_result')
            reason=audit.get('reason','')
            if any(reason.startswith(prefix+':') for prefix in ('URLError','HTTPError','TimeoutError','ConnectionError')):
                raise ApiError(503,'model_unavailable')
            if 'model_digest_mismatch' in reason:raise ApiError(502,'model_identity_mismatch')
            evidence=[];sources={}
            for r in selected:
                try:verify(r.source_path,r.sha256)
                except (ValueError,OSError):raise ApiError(409,'evidence_source_changed')
                sources[r.id]=dict(path=r.source_path,sha256=r.sha256)
                evidence.append(dict(id=r.id,kind=r.kind,source_id='sha256:'+r.sha256,sha256=r.sha256,
                    locator=r.locator,content=r.content,url=f'/v1/runs/{run_id}/evidence/{r.id}'))
            urls={r['id']:r['url'] for r in evidence}
            citations=[dict(claim_index=i,statement=c['statement'],evidence_ids=c['evidence_ids'],
                evidence_urls=[urls[e] for e in c['evidence_ids']]) for i,c in enumerate(result['claims'])]
            phase=(audit.get('phase') or audit.get('raw_prediction',{}).get('phase')) if audit.get('contract_valid') else None
            public=dict(api_version='1.0',run_id=run_id,scenario_id=scenario_id,profile=entry['profile'],
                mode='replay',synthetic=entry['synthetic'],status=result['status'],phase=phase,result=result,
                model=dict(called=audit['model_called'],requests=audit['llm_requests']),
                evidence=evidence,citations=citations,timing=dict(unit='seconds',agent_seconds=agent_seconds,
                    total_seconds=time.perf_counter()-started),
                origins={k:v for k,v in audit.items() if k in ('analysis_origin','observation_origin','comparison_origin',
                    'phase_origin','explanation_origin','citation_origin')},
                limitations=['Historical replay, not current live network state.',
                    'Phase and bounded controller explanation are not proof of initiator or underlying routing cause.',
                    'Synthetic MTU mismatch does not establish routing impact or repair success.'] if entry['profile']=='mtu-observation' else
                    ['Historical replay on the focus link only; not current live network state.',
                     'Operational finding does not establish initiator or hardware cause.'],
                diagnosis_allowed=False,execution_allowed=False,proposed_patch=[])
            public['origins'].setdefault('phase_origin','llm' if phase is not None else 'not_available')
            self.persist(run_id+'/response.json',public)
            self.records[run_id]=dict(public=public,sources=sources)
            return public
        except ApiError as exc:
            self.persist(run_id+'/api-error.json',dict(code=exc.code,http_status=exc.status,run_id=run_id,
                seconds=time.perf_counter()-started,execution_allowed=False))
            raise
        finally:self.lock.release()

def handler(service):
    class Handler(BaseHTTPRequestHandler):
        server_version='ReplayAgent/1.0'
        def send_json(self,status,value):
            raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
            if status==503:self.send_header('Retry-After','1')
            self.end_headers();self.wfile.write(raw)
        def error(self,exc):
            self.close_connection=True
            self.send_json(exc.status,dict(error=dict(code=exc.code),execution_allowed=False))
        def do_GET(self):
            try:
                parsed=urlsplit(self.path)
                if parsed.query:raise ApiError(400,'query_not_supported')
                if parsed.path=='/health':
                    self.send_json(200,dict(status='ok',mode='replay_only',active=service.lock.locked(),
                        model_readiness='not_probed',execution_allowed=False));return
                if parsed.path=='/v1/scenarios':self.send_json(200,service.catalog());return
                match=re.fullmatch(r'/v1/runs/([0-9a-f]{32})(?:/evidence/([A-Za-z0-9_-]{1,32}))?',parsed.path)
                if match:
                    run_id,eid=match.groups()
                    self.send_json(200,service.evidence(run_id,eid) if eid else service.get_record(run_id)['public']);return
                raise ApiError(404,'route_not_found')
            except ApiError as exc:self.error(exc)
            except Exception:self.error(ApiError(500,'internal_error'))
        def do_POST(self):
            try:
                if self.path!='/v1/replays':raise ApiError(404,'route_not_found')
                if self.headers.get('Transfer-Encoding'):raise ApiError(400,'transfer_encoding_not_supported')
                lengths=self.headers.get_all('Content-Length',[])
                if len(lengths)!=1 or not lengths[0].isdigit():raise ApiError(400,'invalid_content_length')
                size=int(lengths[0])
                if not 0<size<=MAX_BODY:raise ApiError(413,'body_too_large')
                if self.headers.get_content_type()!='application/json':raise ApiError(415,'json_required')
                self.connection.settimeout(10)
                try:
                    data=self.rfile.read(size)
                    if len(data)!=size:raise ValueError('incomplete_body')
                    body=json.loads(data.decode('utf-8'),object_pairs_hook=unique_object)
                except (ValueError,UnicodeError):raise ApiError(400,'invalid_json')
                except TimeoutError:raise ApiError(408,'request_timeout')
                if (not isinstance(body,dict) or set(body)!={'scenario_id'} or
                    not isinstance(body['scenario_id'],str) or not re.fullmatch(r'[a-z0-9._-]{1,80}',body['scenario_id'])):
                    raise ApiError(400,'invalid_replay_request')
                self.send_json(201,service.replay(body['scenario_id']))
            except ApiError as exc:self.error(exc)
            except Exception:self.error(ApiError(500,'internal_error'))
        def do_PUT(self):self.error(ApiError(405,'method_not_allowed'))
        do_DELETE=do_PUT
        do_PATCH=do_PUT
    return Handler

def serve(output,port=8765):
    if not 1<=port<=65535:raise ValueError('Invalid port')
    service=ReplayService(output)
    server=ThreadingHTTPServer(('127.0.0.1',port),handler(service));server.daemon_threads=True
    print(json.dumps(dict(listening=f'http://127.0.0.1:{server.server_port}',execution_allowed=False)),flush=True)
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);p.add_argument('--port',type=int,default=8765)
    a=p.parse_args();serve(a.output,a.port)
