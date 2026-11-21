import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rca.catalog import SAMPLE_CATALOG, load_catalog  # noqa: E402
from rca.linter import CommandLinter  # noqa: E402
from rca.topology import SAMPLE_TOPOLOGY, Topology  # noqa: E402


# Default: topologi dan katalog Host 1 (bisa ditimpa RCA_TOPOLOGY / RCA_CATALOG).
@pytest.fixture(scope="session")
def topology():
    return Topology.load()


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()


@pytest.fixture(scope="session")
def linter(topology):
    return CommandLinter(topology)


# Data contoh: dipakai test generik linter dan set uji retrieval.
@pytest.fixture(scope="session")
def sample_catalog():
    return load_catalog(SAMPLE_CATALOG)


@pytest.fixture(scope="session")
def sample_linter():
    return CommandLinter(Topology.load(SAMPLE_TOPOLOGY))
