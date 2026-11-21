"""Topologi lab untuk linter/evaluator.

Sumber default: konfigurasi baseline Host 1 di lab/host1/frr/configs/<router>/frr.conf, dibaca
langsung supaya linter selalu sinkron dengan lab. Bisa juga YAML (data/topology.sample.yaml).
Ganti sumber lewat argumen `Topology.load(path)` atau variabel lingkungan RCA_TOPOLOGY.
"""
from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
HOST1_CONFIGS = ROOT / "lab" / "host1" / "frr" / "configs"
SAMPLE_TOPOLOGY = ROOT / "data" / "topology.sample.yaml"


@dataclass
class Interface:
    name: str
    ips: list[ipaddress.IPv4Interface] = field(default_factory=list)
    peer: str | None = None
    ospf_area: str | None = None

    @property
    def ip(self) -> ipaddress.IPv4Interface | None:
        return self.ips[0] if self.ips else None


@dataclass
class Router:
    name: str
    asn: int
    router_id: str
    interfaces: dict[str, Interface] = field(default_factory=dict)
    # alamat neighbor BGP -> (nama router peer atau "", ASN peer)
    bgp_neighbors: dict[str, tuple[str, int]] = field(default_factory=dict)

    def owns_ip(self, ip: str) -> bool:
        try:
            a = ipaddress.IPv4Address(ip)
        except ValueError:
            return False
        return any(i.ip == a for itf in self.interfaces.values() for i in itf.ips)


class Topology:
    def __init__(self, lab: str = "lab"):
        self.lab = lab
        self.routers: dict[str, Router] = {}

    # ------------------------------------------------------------ pemuatan

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Topology":
        path = Path(path or os.environ.get("RCA_TOPOLOGY") or
                    (HOST1_CONFIGS if HOST1_CONFIGS.is_dir() else SAMPLE_TOPOLOGY))
        return cls.from_frr(path) if path.is_dir() else cls.from_yaml(path)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Topology":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        topo = cls(data.get("lab", "lab"))
        for rname, r in (data.get("routers") or {}).items():
            router = Router(name=rname, asn=int(r["asn"]), router_id=str(r.get("router_id", "")))
            for iname, i in (r.get("interfaces") or {}).items():
                i = i or {}
                ips = i.get("ips") or ([i["ip"]] if i.get("ip") else [])
                area = i.get("ospf_area")
                router.interfaces[iname] = Interface(iname, [ipaddress.IPv4Interface(x) for x in ips], i.get("peer"),
                                                     str(area) if area is not None else None)
            topo.routers[rname] = router
        for s in data.get("bgp_sessions") or []:
            a, b = topo.routers[s["a"]], topo.routers[s["b"]]
            a.bgp_neighbors[str(s["b_addr"])] = (b.name, b.asn)
            b.bgp_neighbors[str(s["a_addr"])] = (a.name, a.asn)
        return topo

    @classmethod
    def from_frr(cls, configs_dir: str | Path, lab: str = "rca") -> "Topology":
        """Baca configs/<router>/frr.conf (konfigurasi baseline yang sehat)."""
        topo = cls(lab)
        for conf in sorted(Path(configs_dir).glob("*/frr.conf")):
            topo.routers[conf.parent.name] = _parse_frr(conf.parent.name, conf.read_text(encoding="utf-8"))
        # isi nama router peer berdasarkan pemilik alamat neighbor
        for r in topo.routers.values():
            for addr, (_, asn) in list(r.bgp_neighbors.items()):
                owner = next((o.name for o in topo.routers.values() if o.owns_ip(addr)), "")
                r.bgp_neighbors[addr] = (owner, asn)
        return topo

    # ------------------------------------------------------------ pencarian

    def has_router(self, router: str) -> bool:
        return router in self.routers

    def has_interface(self, router: str, iface: str) -> bool:
        return router in self.routers and iface in self.routers[router].interfaces

    def interface(self, router: str, iface: str) -> Interface | None:
        r = self.routers.get(router)
        return r.interfaces.get(iface) if r else None


def _parse_frr(name: str, text: str) -> Router:
    router = Router(name=name, asn=0, router_id="")
    cur_if: Interface | None = None
    in_bgp = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("!"):
            continue
        if m := re.fullmatch(r"interface (\S+)", line):
            cur_if = router.interfaces.setdefault(m.group(1), Interface(m.group(1)))
            in_bgp = False
            continue
        if m := re.fullmatch(r"router bgp (\d+)", line):
            router.asn, in_bgp, cur_if = int(m.group(1)), True, None
            continue
        if re.fullmatch(r"router \S+.*", line) or re.fullmatch(r"(route-map|ip prefix-list) .*", line):
            cur_if, in_bgp = None, False
        if line == "exit" and not raw.startswith(" "):
            cur_if, in_bgp = None, False
            continue
        if cur_if is not None:
            if m := re.fullmatch(r"ip address (\S+)", line):
                cur_if.ips.append(ipaddress.IPv4Interface(m.group(1)))
            elif m := re.fullmatch(r"ip ospf area (\S+)", line):
                cur_if.ospf_area = m.group(1)
            elif m := re.fullmatch(r"description \S*_to_(r\d+)_\S+", line):
                cur_if.peer = m.group(1)
        if in_bgp:
            if m := re.fullmatch(r"neighbor (\S+) remote-as (\d+)", line):
                router.bgp_neighbors[m.group(1)] = ("", int(m.group(2)))
            elif m := re.fullmatch(r"bgp router-id (\S+)", line):
                router.router_id = m.group(1)
        if m := re.fullmatch(r"ospf router-id (\S+)", line):
            router.router_id = router.router_id or m.group(1)
    if "lo" in router.interfaces and not router.router_id and router.interfaces["lo"].ips:
        router.router_id = str(router.interfaces["lo"].ips[0].ip)
    return router
