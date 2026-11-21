"""Linter pada topologi Host 1 (lab/host1/frr/configs) dan katalog faults/host1.yaml.

Perintah benar = 30 langkah revert di katalog, baik dalam bentuk `steps` katalog maupun setelah
diubah ke bentuk kontrak agen (host1/agent_contract: interpreter linux_argv / vtysh_commands).
"""
import shlex

import pytest

from rca.catalog import HOST1_CATALOG, load_catalog
from rca.linter import normalize_commands

pytestmark = pytest.mark.skipif(not HOST1_CATALOG.exists(), reason="faults/host1.yaml belum ada")
CATALOG = load_catalog(HOST1_CATALOG) if HOST1_CATALOG.exists() else {}


def to_contract(fix: list[dict]) -> list[dict]:
    """Ubah langkah revert katalog menjadi daftar ProposedCommand versi kontrak agen."""
    out = []
    for block in fix:
        for step in block["steps"]:
            if step["type"] == "shell":
                out.append({"router": block["router"], "interpreter": "linux_argv",
                            "arguments": shlex.split(step["cmd"])})
            else:
                out.append({"router": block["router"], "interpreter": "vtysh_commands",
                            "arguments": list(step["lines"])})
    return out


def test_host1_catalog_shape():
    assert len(CATALOG) == 30
    classes = {f.fault_class for f in CATALOG.values()}
    assert len(classes) == 10
    assert all(sum(f.fault_class == c for f in CATALOG.values()) == 3 for c in classes)


@pytest.mark.parametrize("fault_id", sorted(CATALOG))
def test_revert_steps_pass(linter, fault_id):
    r = linter.lint(CATALOG[fault_id].fix)
    assert r.passed, r.to_dict()


@pytest.mark.parametrize("fault_id", sorted(CATALOG))
def test_revert_as_contract_passes(linter, fault_id):
    r = linter.lint(to_contract(CATALOG[fault_id].fix))
    assert r.passed, r.to_dict()


@pytest.mark.parametrize("fault_id", sorted(CATALOG))
def test_revert_targets_ground_truth_router(fault_id):
    f = CATALOG[fault_id]
    assert {r for r, _, _ in normalize_commands(f.fix)} == {f.router}


def test_full_agent_response_accepted(linter):
    response = {"schema_version": 1, "request_id": "x", "status": "hypothesis",
                "root_cause_hypothesis": "MTU r1 eth1 1400", "claims": [], "missing_evidence": [],
                "proposed_patch": [{"router": "r1", "interface": "eth1", "interpreter": "linux_argv",
                                    "arguments": ["ip", "link", "set", "eth1", "mtu", "1500"],
                                    "evidence_ids": ["e1"], "rationale": "samakan MTU",
                                    "validation_status": "unvalidated"}],
                "execution_allowed": False}
    assert linter.lint(response).passed


def test_short_form_ip_and_vtysh(linter):
    cmds = [{"router": "r1", "interpreter": "ip", "args": ["link", "set", "eth1", "mtu", "1500"]},
            {"router": "r2", "interpreter": "vtysh", "args": ["conf t", "interface eth1", "ip ospf hello-interval 1"]}]
    assert linter.lint(cmds).passed


def _p(router, interp, args):
    return [{"router": router, "interpreter": interp, "arguments": args}]


BAD = [
    # interpreter salah / tidak dikenal
    (_p("r1", "vtysh_commands", ["ip link set eth1 mtu 1500"]), "wrong_interpreter"),
    (_p("r1", "linux_argv", ["conf", "t"]), "wrong_interpreter"),
    (_p("r1", "linux_argv", ["vtysh", "-c", "conf t"]), "shell_injection"),
    (_p("r1", "linux_argv", ["vtysh", "-c", "show"]), "not_allowed"),
    (_p("r1", "bash", ["ip link set eth1 up"]), "wrong_interpreter"),
    # argv yang mencoba lolos ke shell
    (_p("r1", "linux_argv", ["ip", "link", "set", "eth1", "mtu", "1500;reboot"]), "shell_injection"),
    (_p("r1", "linux_argv", ["ip", "link", "set", "eth1 mtu 1500"]), "shell_injection"),
    (_p("r1", "linux_argv", ["sh", "-c", "ip link set eth1 up"]), "shell_injection"),
    (_p("r1", "linux_argv", ["ip", "link", "set", "eth1", "down"]), "dangerous"),
    (_p("r2", "linux_argv", ["ip", "addr", "flush", "dev", "eth1"]), "dangerous"),
    # tidak ada di topologi Host 1
    (_p("r5", "linux_argv", ["ip", "link", "set", "eth3", "up"]), "unknown_interface"),
    (_p("r7", "linux_argv", ["ip", "link", "set", "eth1", "up"]), "unknown_router"),
    (_p("r1", "vtysh_commands", ["conf t", "router bgp 65001", "neighbor 10.255.0.5 remote-as 65001"]),
     "unknown_neighbor"),
    (_p("r1", "vtysh_commands", ["conf t", "router bgp 65001", "neighbor 10.255.0.2 update-source 10.255.0.9"]),
     "unknown_interface"),
    # nilai tidak masuk akal untuk Host 1
    (_p("r1", "vtysh_commands", ["conf t", "router bgp 65002"]), "wrong_asn"),
    (_p("r4", "vtysh_commands", ["conf t", "router bgp 65001", "neighbor 10.0.46.2 remote-as 65002"]), "wrong_asn"),
    (_p("r5", "vtysh_commands", ["conf t", "interface eth1", "ip ospf area 0.0.0.0"]), "area_mismatch"),
    (_p("r1", "vtysh_commands", ["conf t", "interface eth2", "ip ospf area 0.0.0.1"]), "area_mismatch"),
    (_p("r3", "vtysh_commands", ["conf t", "interface eth4", "ip address 10.0.135.1/30"]), "address_mismatch"),
    (_p("r1", "vtysh_commands", ["conf t", "router bgp 65001", "address-family ipv4 unicast",
                                 "network 10.100.9.1/32"]), "address_mismatch"),
    (_p("r1", "linux_argv", ["ip", "link", "set", "eth1", "mtu", "100"]), "value_out_of_range"),
    # berbahaya
    (_p("r3", "vtysh_commands", ["conf t", "no router bgp 65001"]), "dangerous"),
    (_p("r3", "vtysh_commands", ["conf t", "router bgp 65001", "neighbor 10.0.35.2 shutdown"]), "dangerous"),
    (_p("r3", "vtysh_commands", ["clear ip bgp *"]), "dangerous"),
]


@pytest.mark.parametrize("cmds,rule", BAD, ids=[f"{i:02d}-{b[1]}" for i, b in enumerate(BAD)])
def test_host1_bad_commands(linter, cmds, rule):
    r = linter.lint(cmds)
    assert not r.passed and rule in r.rules, r.to_dict()
