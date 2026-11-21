"""Run Host 1 Python commands from any directory with the selected interpreter.

Example: private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.api --help
"""
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env['PYTHONPATH'] = str(root / 'host1') + os.pathsep + env.get('PYTHONPATH', '')
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python scripts/host1.py <Python arguments>')
    raise SystemExit(subprocess.call([sys.executable, *sys.argv[1:]], cwd=root, env=env))


if __name__ == '__main__':
    main()
