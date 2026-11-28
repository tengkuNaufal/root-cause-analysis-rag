#!/usr/bin/env bash
# Persistent loopback services for Host 1. No lab deploy, faults or benchmark is started.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
root=$PWD
python=${HOST1_PYTHON:-$root/private/.venv-retriever-wsl/bin/python}
export PYTHONPATH="$root/host1:$root:$root/private/live-agent-deps${PYTHONPATH:+:$PYTHONPATH}"
case ${1:-status} in
  _api)
    session=$(cat private/live-agent/latest.txt)
    export LIVE_API_TOKEN=$(cat "$session/token.txt")
    printf '{"pid":%s,"port":8766,"mode":"live","token_file":"token.txt"}\n' "$$" >"$session/process.json"
    exec "$python" -m live_api.server --output "$session/jobs" --port 8766 --exclusive-model-session >>"$session/server.log" 2>&1
    ;;
  _model)
    mkdir -p private/live-services
    exec bash host1/ollama_host/serve.sh >>private/live-services/ollama.log 2>&1
    ;;
  start-model)
    "$python" -c 'import socket; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(("127.0.0.1",11434)); s.close()'
    tmux new-session -d -s rca-model "bash $(printf '%q' "$root/host1/live_api/manage.sh") _model"
    ;;
  start-api)
    "$python" -c 'import socket; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(("127.0.0.1",8766)); s.close()'
    # Keep a session across controlled restarts so requests can still be reconciled.
    "$python" - <<'PY'
from pathlib import Path
import datetime, secrets, os
root=Path.cwd(); latest=root/'private/live-agent/latest.txt'
if not latest.exists():
    session=root/'private/live-agent'/('tmux-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    session.mkdir(parents=True)
    token=session/'token.txt';token.write_text(secrets.token_urlsafe(32));os.chmod(token,0o600)
    latest.write_text(str(session.relative_to(root)))
session=(root/latest.read_text().strip()).resolve()
if not session.is_relative_to(root/'private') or not (session/'token.txt').is_file():
    raise SystemExit('Invalid private API session')
PY
    tmux new-session -d -s rca-api "bash $(printf '%q' "$root/host1/live_api/manage.sh") _api"
    "$python" - <<'PY'
import socket,time
for _ in range(120):
    try:
        with socket.create_connection(('127.0.0.1',8766),timeout=.5):break
    except OSError:time.sleep(.25)
else:raise SystemExit('API did not start within 30 seconds; inspect private server.log')
PY
    ;;
  status)
    tmux list-sessions 2>/dev/null || true
    "$python" - <<'PY'
import json, urllib.request
from pathlib import Path
root=Path.cwd();session=root/(root/'private/live-agent/latest.txt').read_text().strip()
request=urllib.request.Request('http://127.0.0.1:8766/health',headers={'Authorization':'Bearer '+(session/'token.txt').read_text().strip()})
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=10) as response:
    print(json.dumps(json.load(response),indent=2))
PY
    ;;
  *) echo 'Usage: bash host1/live_api/manage.sh start-model|start-api|status'; exit 2 ;;
esac
