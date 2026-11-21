# Client untuk API diagnosis live Host 1 (kontrak live.v1-draft2 di docs/host1/LIVE-API-DRAFT.md).
# Cuma pakai stdlib biar bisa jalan di WSL Host 1 maupun laptop tanpa dependency tambahan.
import hashlib
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

CONTRACT = "live.v1-draft2"
TERMINAL = {"completed", "failed", "interrupted"}
EVIDENCE_FIELDS = ("id", "kind", "source_id", "source_sha256", "locator")


class ApiError(Exception):
    def __init__(self, status, code, retryable=False):
        super().__init__(f"HTTP {status} {code}")
        self.status, self.code, self.retryable = status, code, retryable


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_sha256(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_request(variant, symptom_detected_at_utc, lab="rca"):
    return {"contract_version": CONTRACT, "request_id": str(uuid.uuid4()), "lab": lab, "variant": variant,
            "symptom_detected_at_utc": symptom_detected_at_utc, "execution_allowed": False}


class LiveClient:
    def __init__(self, base_url, token, http_timeout=15):
        url = urllib.parse.urlsplit(base_url)
        if url.scheme not in ("http", "https") or not url.hostname or url.path not in ("", "/") \
                or url.query or url.fragment or url.username:
            raise ValueError("URL API harus berupa root http(s) tanpa path, query, atau kredensial")
        if not token or any(c.isspace() for c in token):
            raise ValueError("Token API kosong atau berisi spasi")
        self.base = f"{url.scheme}://{url.netloc}"
        self._token = token
        self.http_timeout = http_timeout
        # Mematikan proxy sistem soalnya API cuma ada di LAN/Tailscale.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _call(self, method, path, body=None):
        if not path.startswith("/") or path.startswith("//") or ".." in path:
            raise ValueError(f"path API tidak valid: {path}")
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(req, timeout=self.http_timeout) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read() or b"null") or {}
            except ValueError:
                err = {}
            detail = err.get("error") or {}
            raise ApiError(e.code, detail.get("code", "http_error"), bool(detail.get("retryable"))) from None

    def health(self):
        return self._call("GET", "/health")[1]

    def capabilities(self):
        return self._call("GET", "/v1/capabilities")[1]

    def submit(self, request):
        return self._call("POST", "/v1/diagnoses", request)[1]

    def job(self, job_id):
        return self._call("GET", f"/v1/diagnoses/{urllib.parse.quote(job_id)}")[1]

    def job_by_request(self, request_id):
        try:
            return self._call("GET", f"/v1/diagnoses/by-request/{urllib.parse.quote(request_id)}")[1]
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    def evidence(self, url):
        return self._call("GET", url)[1]


TRANSPORT_ERRORS = (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError)


# Mengirim request; kalau respons POST hilang, job dicari lewat request_id dulu sebelum kirim ulang.
def submit_once(client, request):
    try:
        return client.submit(request)
    except TRANSPORT_ERRORS:
        pass
    except ApiError as e:
        if e.status < 500 or e.code in ("agent_busy", "live_not_ready", "replay_session_reserved"):
            raise
    job = client.job_by_request(request["request_id"])
    if job is not None:
        return job
    # Mengulang POST dengan request_id dan payload yang sama, server menjamin gak bikin job ganda.
    return client.submit(request)


# Polling sampai job terminal atau deadline monotonic habis, error transport sesaat dilewati aja.
def wait_terminal(client, job, deadline, poll=1.0, clock=time.monotonic):
    while job.get("state") not in TERMINAL:
        if clock() >= deadline:
            return job, False
        time.sleep(poll)
        try:
            job = client.job(job["job_id"])
        except TRANSPORT_ERRORS:
            continue
    return job, True


# Mengambil tiap evidence di manifest lalu mencocokkan identitasnya. Content gak dibandingin
# karena manifest gak memuatnya.
def verify_evidence(client, job):
    checked, problems = 0, []
    for item in job.get("evidence") or []:
        try:
            got = client.evidence(item["url"])
        except (ApiError, *TRANSPORT_ERRORS) as e:
            problems.append(f"{item.get('id')}: {e}")
            continue
        diff = [f for f in EVIDENCE_FIELDS if got.get(f) != item.get(f)]
        if diff:
            problems.append(f"{item.get('id')}: beda di {', '.join(diff)}")
        else:
            checked += 1
    return {"total": len(job.get("evidence") or []), "verified": checked, "problems": problems}
