import pytest
from scripts.lab_lock import lab_lock, LabBusy

def test_contending_executor_cannot_acquire_runner_lock(tmp_path):
    with lab_lock('rca', tmp_path):
        with pytest.raises(LabBusy):
            with lab_lock('rca', tmp_path):
                pytest.fail('Concurrent lab owner was admitted')
        with lab_lock('replica', tmp_path):
            pass
    with lab_lock('rca', tmp_path):
        pass

def test_exception_releases_lab_lock(tmp_path):
    with pytest.raises(ValueError):
        with lab_lock('rca', tmp_path):
            raise ValueError('interrupted')
    with lab_lock('rca', tmp_path):
        pass
