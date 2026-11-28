#!/usr/bin/env bash
# Start an explicitly requested local run in tmux; SSH may disconnect safely.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
root=$PWD
python=${HOST1_PYTHON:-$root/private/.venv-retriever-wsl/bin/python}
export PYTHONPATH="$root/host1:$root:$root/private/live-agent-deps${PYTHONPATH:+:$PYTHONPATH}"
if [ "${1:-}" = _run ]; then
  exec "$python" - "$2" <<'PY'
import argparse,datetime,json,os,subprocess,sys
from pathlib import Path
root=Path.cwd();session=Path(sys.argv[1]).resolve()
assert session.is_relative_to(root/'private')
args=json.loads((session/'arguments.json').read_text())
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--variants')
selected,_=parser.parse_known_args(args)
regex_only=selected.variants is not None and set(selected.variants.split(','))=={'rule_based'}
api_args=[];env=dict(os.environ,PYTHONUNBUFFERED='1')
if not regex_only:
    api=root/(root/'private/live-agent/latest.txt').read_text().strip()
    assert api.resolve().is_relative_to(root/'private')
    env['LIVE_API_TOKEN']=(api/'token.txt').read_text().strip()
    api_args=['--api','http://127.0.0.1:8766']
state=dict(started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),exit_code=None)
with (session/'runner.log').open('w') as log:
    process=subprocess.Popen([sys.executable,'scripts/bench.py',*api_args,*args],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    state['pid']=process.pid;(session/'process.json').write_text(json.dumps(state))
    for line in process.stdout:
        print(line,end='',flush=True);log.write(line);log.flush()
    state['exit_code']=process.wait()
state['completed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
(session/'process.json').write_text(json.dumps(state))
print('Runner finished, exit code '+str(state['exit_code'])+'. Results remain local.',flush=True)
raise SystemExit(state['exit_code'])
PY
fi
if [ "$#" -eq 0 ]; then
  echo 'Usage: bash scripts/start-benchmark.sh --out PRIVATE_OR_IGNORED_OUTPUT [bench.py options]'
  exit 2
fi
if tmux has-session -t bench 2>/dev/null; then
  echo 'tmux bench already exists; inspect its process.json and held jobs before closing/reusing it.'
  exit 1
fi
session=$("$python" - "$@" <<'PY'
import datetime,json,sys,uuid
from pathlib import Path
args=sys.argv[1:];root=Path.cwd()
if any(a=='--api' or a.startswith('--api=') for a in args) or '--out' not in args:
    raise SystemExit('Supply --out; API is fixed to local Host 1')
out=(root/args[args.index('--out')+1]).resolve()
if not any(out.is_relative_to(root/part) for part in ('private','data/host2')):
    raise SystemExit('Run output must stay in private/ or ignored data/host2/')
session=root/'private/live-runner'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
session.mkdir(parents=True);(session/'arguments.json').write_text(json.dumps(args))
(root/'private/live-runner/latest.txt').write_text(str(session.relative_to(root)))
print(str(session))
PY
)
# This pane is newly created here, never an existing benchmark pane.
tmux new-session -d -s bench
tmux set-option -t bench remain-on-exit on
tmux respawn-pane -k -t bench "bash $(printf '%q' "$root/scripts/start-benchmark.sh") _run $(printf '%q' "$session")"
echo 'Started detached tmux bench. Monitor with tmux attach -r -t bench; token stays private.'
