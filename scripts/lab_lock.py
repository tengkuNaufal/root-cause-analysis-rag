"""A single advisory lab lock shared by benchmark, demo and local executor."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

class LabBusy(RuntimeError):
    pass

@contextmanager
def lab_lock(lab='rca', directory=None):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', lab):
        raise ValueError('Invalid lab name')
    folder = Path(directory) if directory else ROOT / 'private' / 'lab-locks'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (lab + '.lock')).open('a+b') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LabBusy('Lab ' + lab + ' is already owned by another runner or executor') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
