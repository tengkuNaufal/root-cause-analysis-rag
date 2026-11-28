"""Unit test command linter pada topologi dan katalog CONTOH (data/*.sample.yaml).

Bagian 1: ke-30 perbaikan benar di katalog harus lolos.
Bagian 2: perintah berbahaya / salah harus ditolak dengan aturan yang tepat.
Jalankan terhadap katalog & topologi final dengan env RCA_CATALOG dan RCA_TOPOLOGY.
"""
import json

import pytest

from rca.catalog import SAMPLE_CATALOG, load_catalog
from rca.linter import lint, main, normalize_commands

CATALOG = load_catalog(SAMPLE_CATALOG)


def test_catalog_has_30_faults_10_classes():
    assert len(CATALOG) == 30
    classes = {f.fault_class for f in CATALOG.values()}
    assert len(classes) == 10
    for c in classes:
        assert sum(f.fault_class == c for f in CATALOG.values()) == 3


@pytest.mark.parametrize("fault_id", sorted(CATALOG))
def test_catalog_fix_passes(sample_linter, fault_id):
    result = sample_linter.lint(CATALOG[fault_id].fix)
    assert result.passed, result.to_dict()


@pytest.mark.parametrize("fault_id", sorted(CATALOG))
def test_catalog_fix_targets_fault_router(fault_id):
    fault = CATALOG[fault_id]
    routers = {r for r, _, _ in normalize_commands(fault.fix)}
    assert fault.router in routers


# ------------------------------------------------------------------ contoh buruk
# (router, perintah, aturan yang diharapkan)
BAD = [
    # perintah berbahaya
    ("r1", ["configure terminal", "no router ospf"], "dangerous"),
    ("r1", ["configure terminal", "no router bgp 65001"], "dangerous"),
    ("r2", ["reload"], "dangerous"),
    ("r2", ["write erase"], "dangerous"),
    ("r3", ["configure terminal", "no interface eth1"], "dangerous"),
    ("r3", ["clear ip bgp *"], "dangerous"),
    ("r3", ["clear ip ospf process"], "dangerous"),
    ("r4", ["ip link set dev eth1 down"], "dangerous"),
    ("r4", ["ip link delete eth2"], "dangerous"),
    ("r4", ["ip route flush all"], "dangerous"),
    ("r5", ["rm -rf /etc/frr"], "dangerous"),
    ("r5", ["sudo systemctl restart frr"], "dangerous"),
    ("r5", ["docker restart r5"], "dangerous"),
    ("r6", ["configure terminal", "interface eth1", "shutdown"], "dangerous"),
    ("r6", ["configure terminal", "router bgp 65002", "neighbor 10.255.0.4 shutdown"], "dangerous"),
    ("r6", ["configure terminal", "router bgp 65002", "no neighbor 10.255.0.4"], "dangerous"),
    ("r6", ["configure terminal", "interface eth1", "no ip address"], "dangerous"),
    ("r1", ["do reload"], "dangerous"),
    # shell yang disambung
    ("r1", ["ip link set dev eth1 mtu 1500; reboot"], "shell_injection"),
    ("r1", ["ip link set dev eth1 mtu 1500 && rm -rf /"], "shell_injection"),
    ("r1", ["ip link set dev eth1 mtu $(cat /x)"], "shell_injection"),
    ("r1", ["show running-config | tee /tmp/x"], "shell_injection"),
    ("r1", ["ip link set dev eth1 mtu 1500 `id`"], "shell_injection"),
    ("r1", ["show run > /etc/frr/frr.conf"], "shell_injection"),
    ("r1", ["vtysh -c 'conf t' -c 'no router ospf'"], "dangerous"),
    # router / interface / neighbor tidak ada
    ("r9", ["ip link set dev eth1 mtu 1500"], "unknown_router"),
    ("", ["ip link set dev eth1 mtu 1500"], "unknown_router"),
    ("r4", ["ip link set dev eth3 mtu 1500"], "unknown_interface"),
    ("r1", ["configure terminal", "interface eth9", "no shutdown"], "unknown_interface"),
    ("r1", ["configure terminal", "router ospf", "no passive-interface eth7"], "unknown_interface"),
    ("r3", ["configure terminal", "router bgp 65001", "neighbor 10.0.99.2 remote-as 65002"], "unknown_neighbor"),
    ("r3", ["clear ip bgp 10.9.9.9 soft"], "unknown_neighbor"),
    # nilai tidak masuk akal
    ("r1", ["ip link set dev eth1 mtu 100"], "value_out_of_range"),
    ("r1", ["ip link set dev eth1 mtu 65000"], "value_out_of_range"),
    ("r1", ["configure terminal", "interface eth1", "mtu 99999"], "value_out_of_range"),
    ("r2", ["configure terminal", "interface eth1", "ip ospf hello-interval 0"], "value_out_of_range"),
    ("r2", ["configure terminal", "interface eth1", "ip ospf dead-interval 99999"], "value_out_of_range"),
    ("r2", ["configure terminal", "interface eth1", "ip ospf hello-interval 30", "ip ospf dead-interval 10"],
     "value_out_of_range"),
    ("r1", ["configure terminal", "interface eth1", "ip ospf message-digest-key 300 md5 abc"], "value_out_of_range"),
    ("r1", ["configure terminal", "ip prefix-list X seq 5 permit 10.0.0.1/8"], "value_out_of_range"),
    ("r1", ["configure terminal", "ip prefix-list X seq 5 permit 10.0.0.0/8 le 40"], "value_out_of_range"),
    ("r1", ["configure terminal", "route-map RM permit 10", "set local-preference 99999999999"], "value_out_of_range"),
    ("r3", ["configure terminal", "router bgp 65001", "neighbor 10.0.34.2 timers 90 30"], "value_out_of_range"),
    ("r2", ["configure terminal", "interface eth1", "ip address 10.0.12.9/30"], "address_mismatch"),
    ("r2", ["configure terminal", "interface eth1", "no ip address 10.0.12.2/30"], "address_mismatch"),
    ("r1", ["configure terminal", "interface eth2", "ip ospf area 0.0.0.1"], "area_mismatch"),
    ("r1", ["configure terminal", "interface eth3", "ip ospf area 0"], "area_mismatch"),
    ("r1", ["configure terminal", "router ospf", "network 10.0.13.0/30 area 1"], "area_mismatch"),
    ("r3", ["configure terminal", "router bgp 65002"], "wrong_asn"),
    ("r3", ["configure terminal", "router bgp 65001", "neighbor 10.0.34.2 remote-as 65001"], "wrong_asn"),
    ("r1", ["configure terminal", "router bgp 65001", "neighbor 10.255.0.2 remote-as external"], "wrong_asn"),
    # di luar pola yang diizinkan
    ("r1", ["configure terminal", "hostname pwned"], "not_allowed"),
    ("r1", ["configure terminal", "router ospf", "passive-interface default"], "not_allowed"),
    ("r1", ["configure terminal", "router ospf", "passive-interface eth1"], "not_allowed"),
    ("r1", ["configure terminal", "username admin nopassword"], "not_allowed"),
    ("r1", ["configure terminal", "line vty"], "not_allowed"),
    ("r1", ["configure terminal", "router rip"], "not_allowed"),
    ("r1", ["ip addr add 10.0.12.1/30 dev eth1"], "not_allowed"),
    ("r1", ["mtu 1500"], "not_allowed"),  # mtu di luar konteks interface
    ("r1", ["configure terminal", "interface eth1", "mtu 1500"], "wrong_interpreter"),
    ("r1", ["configure terminal", "interface eth1", "ip mtu 1500"], "wrong_interpreter"),
]


@pytest.mark.parametrize("router,commands,rule", BAD, ids=[f"{i:02d}-{b[2]}" for i, b in enumerate(BAD)])
def test_bad_commands_rejected(sample_linter, router, commands, rule):
    result = sample_linter.lint([{"router": router, "commands": commands}])
    assert not result.passed
    assert rule in result.rules, result.to_dict()


def test_bad_line_inside_good_fix_is_rejected(sample_linter):
    fix = CATALOG["F04"].fix[0]
    cmds = list(fix["commands"]) + ["exit", "no router ospf"]
    result = sample_linter.lint([{"router": fix["router"], "commands": cmds}])
    assert not result.passed and "dangerous" in result.rules
    assert len(result.violations) == 1


def test_empty_commands_not_passed(sample_linter):
    assert not sample_linter.lint([]).passed
    assert "no_commands" in sample_linter.lint([{"router": "r1", "commands": []}]).rules


# ------------------------------------------------------------------ bentuk masukan lain


def test_flat_format_keeps_context(sample_linter):
    cmds = [
        {"router": "r2", "command": "configure terminal"},
        {"router": "r2", "command": "interface eth1"},
        {"router": "r2", "command": "ip ospf hello-interval 10"},
    ]
    assert sample_linter.lint(cmds).passed


def test_dict_format_and_multiline_string(sample_linter):
    assert sample_linter.lint({"r1": "configure terminal\ninterface eth3\nno shutdown"}).passed


def test_vtysh_wrapper_expanded(sample_linter):
    cmd = "vtysh -c 'configure terminal' -c 'interface eth1' -c 'ip ospf hello-interval 10'"
    assert sample_linter.lint([{"router": "r2", "commands": [cmd]}]).passed


def test_implicit_parent_mode_like_vtysh(sample_linter):
    # pindah dari mode interface langsung ke router ospf tanpa exit
    cmds = ["configure terminal", "interface eth2", "no ip ospf passive", "router ospf", "no passive-interface eth2"]
    assert sample_linter.lint([{"router": "r2", "commands": cmds}]).passed


def test_alternative_valid_fixes(sample_linter):
    ok = [
        ("r1", ["configure terminal", "interface eth1", "ip ospf mtu-ignore"]),
        ("r3", ["configure terminal", "router bgp 65001", "neighbor 10.0.34.2 remote-as external"]),
        ("r1", ["configure terminal", "router ospf", "network 10.0.13.0/30 area 0"]),
        ("r1", ["configure terminal", "route-map RCA-LP permit 10", "set local-preference 200"]),
        ("r1", ["show ip ospf neighbor", "show bgp summary"]),
        ("r1", ["configure terminal", "interface eth1", "ip ospf hello-interval 10", "ip ospf dead-interval 40"]),
    ]
    for router, cmds in ok:
        r = sample_linter.lint([{"router": router, "commands": cmds}])
        assert r.passed, (router, cmds, r.to_dict())


def test_output_contract(sample_linter):
    out = lint([{"router": "r1", "commands": ["reload"]}], sample_linter.topo)
    assert set(out) == {"passed", "violations"}
    assert out["passed"] is False
    assert set(out["violations"][0]) == {"router", "line", "command", "rule", "message"}
    json.dumps(out)


def test_cli_accepts_agent_answer(tmp_path, capsys):
    answer = {"router": "r1", "root_cause": "mtu_mismatch", "confidence": 0.9, "evidence_ids": ["e1"],
              "commands": [{"router": "r1", "commands": ["ip link set dev eth1 mtu 1500"]}], "explanation": "x"}
    p = tmp_path / "a.json"
    p.write_text(json.dumps(answer))
    assert main([str(p)]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True
