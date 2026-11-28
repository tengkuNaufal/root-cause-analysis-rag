"""Command linter: memeriksa perintah perbaikan dari agen sebelum dijalankan ke router.

Masukan: daftar perintah beserta router tujuan, dalam salah satu bentuk berikut
    [{"router": "r1", "commands": ["configure terminal", "interface eth1", "mtu 1500"]}]
    [{"router": "r1", "command": "ip link set dev eth1 mtu 1500"}]
    {"r1": ["..."], "r2": ["..."]}

Keluaran (kontrak dengan runner):
    {"passed": true|false, "violations": [{"router", "line", "command", "rule", "message"}]}

Aturan:
  1. router dan interface ada di topologi (unknown_router, unknown_interface, unknown_neighbor)
  2. perintah termasuk pola yang diizinkan (not_allowed)
  3. nilainya masuk akal (value_out_of_range, address_mismatch, area_mismatch, wrong_asn)
  4. tidak ada perintah berbahaya (dangerous, shell_injection)

Perilaku konteks mengikuti vtysh: perintah yang tidak dikenali di mode saat ini
dicoba di mode induknya (mis. `router ospf` boleh dari dalam mode interface).
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import shlex
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from rca.topology import Topology

# Bump on any policy/allowlist semantic change; source digest is recorded separately.
POLICY_VERSION = 'host1-policy-v1'
POLICY_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

# ------------------------------------------------------------------ hasil


@dataclass
class Violation:
    router: str
    line: int
    command: str
    rule: str
    message: str


@dataclass
class LintResult:
    passed: bool
    violations: list[Violation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "violations": [asdict(v) for v in self.violations]}

    @property
    def rules(self) -> set[str]:
        return {v.rule for v in self.violations}


# ------------------------------------------------------------------ batas nilai

LIMITS = {
    "mtu": (1280, 9216),
    "hello": (1, 300),
    "dead": (2, 1200),
    "cost": (1, 65535),
    "retransmit": (1, 65535),
    "md5_key_id": (1, 255),
    "asn": (1, 4294967295),
    "seq": (1, 4294967295),
    "local_pref": (0, 4294967295),
    "metric": (0, 4294967295),
    "multihop": (1, 255),
    "bgp_keepalive": (0, 65535),
    "bgp_hold": (0, 65535),
}

NAME_RE = r"[A-Za-z0-9_.\-]{1,63}"
IP_RE = r"\d{1,3}(?:\.\d{1,3}){3}"
PFX_RE = IP_RE + r"/\d{1,2}"
AREA_RE = r"(?:" + IP_RE + r"|\d+)"

# Pola berbahaya diperiksa lebih dulu pada baris mentah, di mode mana pun.
SHELL_META = re.compile(r"[;&|`$<>\\]|\$\(")
DANGEROUS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^no\s+router\s+(ospf|ospf6|bgp|rip|ripng|isis|eigrp)\b"), "menghapus seluruh proses routing"),
    (re.compile(r"^(reload|reboot|halt|poweroff|init\s+\d)\b"), "me-restart / mematikan router"),
    (re.compile(r"^(write\s+erase|erase\b|delete\b|copy\s+\S+\s+startup)"), "menghapus / menimpa konfigurasi tersimpan"),
    (re.compile(r"^no\s+interface\b"), "menghapus interface"),
    (re.compile(r"^clear\s+ip\s+ospf\s+(\d+\s+)?process"), "me-reset seluruh proses OSPF"),
    (re.compile(r"^clear\s+(ip\s+)?bgp\s+(ipv4\s+unicast\s+)?\*"), "me-reset semua sesi BGP"),
    (re.compile(r"^ip\s+link\s+set\s+(dev\s+)?\S+\s+down\b"), "mematikan interface"),
    (re.compile(r"^ip\s+link\s+(del|delete)\b"), "menghapus interface"),
    (re.compile(r"^ip\s+(-\d\s+)?(route|addr|address|neigh)\s+(flush|del|delete)\b"), "menghapus rute / alamat lewat shell"),
    (re.compile(r"^(sudo|su|rm|mv|dd|mkfs|kill|killall|pkill|systemctl|service|docker|bash|sh|python\d*|"
                r"curl|wget|nc|chmod|chown|iptables|nft|tc|sysctl|shutdown\s+-)\b"), "perintah shell di luar daftar izin"),
    (re.compile(r"^shutdown$"), "mematikan interface"),
    (re.compile(r"^neighbor\s+\S+\s+shutdown\b"), "mematikan sesi BGP"),
    (re.compile(r"^no\s+neighbor\s+" + IP_RE + r"$"), "menghapus neighbor BGP seluruhnya"),
    (re.compile(r"^no\s+ip\s+address$"), "menghapus semua alamat interface"),
]


# ------------------------------------------------------------------ util


def _in(value: int, key: str) -> bool:
    lo, hi = LIMITS[key]
    return lo <= value <= hi


def _norm_area(area: str) -> str:
    if area.isdigit():
        return str(ipaddress.IPv4Address(int(area)))
    return str(ipaddress.IPv4Address(area))


def _valid_ip(s: str) -> bool:
    try:
        ipaddress.IPv4Address(s)
        return True
    except ValueError:
        return False


# Jenis interpreter: "vtysh" (baris perintah vtysh), "shell" (satu argv Linux), "any" (tidak disebut).
VTYSH_NAMES = {"vtysh", "vtysh_commands"}
SHELL_NAMES = {"linux_argv", "ip", "shell", "linux"}


def normalize_commands(commands) -> list[tuple[str, str, list[str]]]:
    """Ubah berbagai bentuk masukan menjadi [(router, interpreter, [baris, ...]), ...].

    Bentuk yang diterima:
      kontrak agen Host 1  {"router", "interpreter": "linux_argv"|"vtysh_commands", "arguments": [...]}
      respons agen utuh    {"proposed_patch": [ProposedCommand, ...], ...}
      langkah katalog      {"router", "steps": [{"type": "shell", "cmd": "..."}, {"type": "vtysh", "lines": [...]}]}
      bentuk singkat       {"router", "interpreter": "ip"|"vtysh", "args": [...]}
      bentuk lama          {"router", "commands": [...]} / {"router", "command": "..."} / {"r1": [...]}
    """
    blocks: list[tuple[str, str, list[str]]] = []
    if commands is None:
        return blocks
    if isinstance(commands, dict) and "proposed_patch" in commands:
        commands = commands["proposed_patch"]
    if isinstance(commands, dict) and not ({"commands", "router", "steps", "arguments", "args"} & set(commands)):
        for router, lines in commands.items():
            blocks.append((str(router), "any", _as_lines(lines)))
        return blocks
    if isinstance(commands, dict):
        commands = [commands]
    for item in commands:
        if isinstance(item, str):
            blocks.append(("", "any", _as_lines(item)))
            continue
        router = str(item.get("router") or item.get("target") or item.get("device") or "")
        if "steps" in item:  # langkah revert/fix di katalog
            for step in item["steps"] or []:
                kind = "shell" if str(step.get("type", "")).lower() in SHELL_NAMES else "vtysh"
                body = step.get("lines") if kind == "vtysh" else step.get("cmd", step.get("argv"))
                if kind == "shell" and isinstance(body, list):
                    body = [_argv_line(body)]
                blocks.append((router, kind, _as_lines(body)))
            continue
        interp = str(item.get("interpreter") or "").lower()
        if interp or "arguments" in item or "args" in item:
            args = item.get("arguments", item.get("args", []))
            if isinstance(args, str):
                args = [args]
            if interp in SHELL_NAMES:
                argv = list(args)
                if interp == "ip" and argv and argv[0] != "ip":
                    argv = ["ip", *argv]
                blocks.append((router, "shell", [_argv_line(argv)]))
            elif interp in VTYSH_NAMES:
                blocks.append((router, "vtysh", _as_lines(args)))
            else:
                blocks.append((router, f"unknown:{interp}", _as_lines(args)))
            continue
        lines = _as_lines(item.get("commands", item.get("command", item.get("cmd", []))))
        # Gabungkan blok berurutan untuk router yang sama agar konteks terbawa.
        if blocks and blocks[-1][0] == router and blocks[-1][1] == "any" and "command" in item:
            blocks[-1][2].extend(lines)
        else:
            blocks.append((router, "any", lines))
    return blocks


def _argv_line(argv: list) -> str:
    """argv Linux tidak pernah dijalankan lewat shell; elemen berspasi/metakarakter tetap ditolak."""
    parts = [str(a) for a in argv]
    if any(not p or re.search(r"\s", p) or SHELL_META.search(p) for p in parts):
        return "\x00" + " ".join(parts)  # penanda argv tidak valid
    return " ".join(parts)


def _as_lines(lines) -> list[str]:
    if isinstance(lines, str):
        lines = lines.splitlines()
    out: list[str] = []
    for line in lines or []:
        out.extend(_expand_vtysh(str(line)))
    return out


def _expand_vtysh(line: str) -> list[str]:
    """`vtysh -c 'conf t' -c 'interface eth1'` -> ['conf t', 'interface eth1']."""
    stripped = line.strip()
    if not re.match(r"^(docker\s+exec\s+\S+\s+)?vtysh\b", stripped):
        return [line]
    if SHELL_META.search(stripped.replace("\\", "")):
        return [line]  # biarkan pemeriksa shell_injection yang menolak
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return [line]
    parts = [tokens[i + 1] for i, t in enumerate(tokens[:-1]) if t == "-c"]
    return parts or [line]


# ------------------------------------------------------------------ linter


@dataclass
class _State:
    router: str
    mode: str = "top"  # top | interface | ospf | bgp | bgp_af | route_map
    iface: str | None = None
    # per-interface: timer yang diset di batch ini, untuk cek dead > hello
    timers: dict[str, dict[str, int]] = field(default_factory=dict)


Handler = Callable[["CommandLinter", _State, re.Match], "str | tuple[str, str] | None"]

PARENT = {"interface": "top", "ospf": "top", "bgp": "top", "route_map": "top", "bgp_af": "bgp", "top": None, "shell": None}


class CommandLinter:
    def __init__(self, topology: Topology):
        self.topo = topology
        self.rules: dict[str, list[tuple[re.Pattern, Handler]]] = {m: [] for m in PARENT}
        self._register()

    # ------------------------------------------------------------ API

    def lint(self, commands) -> LintResult:
        violations: list[Violation] = []
        blocks = normalize_commands(commands)
        total = sum(len([l for l in lines if l.strip()]) for _, _, lines in blocks)
        if total == 0:
            violations.append(Violation("", 0, "", "no_commands", "tidak ada perintah perbaikan"))
        for router, kind, lines in blocks:
            if not self.topo.has_router(router):
                violations.append(Violation(router, 0, "", "unknown_router",
                                            f"router '{router}' tidak ada di topologi {self.topo.lab}"))
                continue
            if kind.startswith("unknown:"):
                violations.append(Violation(router, 0, "", "wrong_interpreter",
                                            f"interpreter '{kind[8:]}' tidak dikenal (linux_argv / vtysh_commands)"))
                continue
            state = _State(router)
            for n, raw in enumerate(lines, start=1):
                v = self._lint_line(state, raw, kind)
                if v:
                    rule, msg = v
                    violations.append(Violation(router, n, raw.lstrip("\x00").strip(), rule, msg))
        return LintResult(passed=not violations, violations=violations)

    # ------------------------------------------------------------ satu baris

    def _match(self, mode: str, low: str) -> bool:
        return any(p.fullmatch(low) for p, _ in self.rules[mode])

    def _lint_line(self, st: _State, raw: str, kind: str = "any") -> tuple[str, str] | None:
        if raw.startswith("\x00"):
            return ("shell_injection", "argv berisi elemen kosong, berspasi, atau karakter shell")
        line = re.sub(r"\s+", " ", raw.strip())
        if not line or line.startswith("!") or line.startswith("#"):
            return None
        if "\n" in raw.strip() or SHELL_META.search(line):
            return ("shell_injection", "karakter shell (; & | ` $ < > \\) tidak diizinkan")
        low = line.lower()
        low = re.sub(r"^do ", "", low)
        for pat, why in DANGEROUS:
            if pat.search(low):
                return ("dangerous", f"perintah berbahaya: {why}")
        # Perintah Linux (ip link) hanya lewat linux_argv; perintah vtysh tidak boleh lewat argv.
        if kind in ("shell", "any"):
            for pat, handler in self.rules["shell"]:
                m = pat.fullmatch(low)
                if m:
                    err = handler(self, st, m)
                    return err if isinstance(err, tuple) else (("value_out_of_range", err) if err else None)
            if kind == "shell":
                if any(self._match(m, low) for m in ("top", "interface", "ospf", "bgp", "bgp_af", "route_map")):
                    return ("wrong_interpreter", "perintah vtysh harus dikirim sebagai vtysh_commands, bukan linux_argv")
                return ("not_allowed", "linux_argv hanya boleh `ip link set [dev] IF mtu N` atau `ip link set [dev] IF up`")
        elif self._match("shell", low):
            return ("wrong_interpreter", "perintah `ip link` harus dikirim sebagai linux_argv, bukan vtysh")
        mode = st.mode
        while mode is not None:
            for pat, handler in self.rules[mode]:
                m = pat.fullmatch(low)
                if m:
                    if mode != st.mode:  # keluar implisit ke mode induk, seperti vtysh
                        st.mode = mode
                        if mode in ("top", "bgp"):
                            st.iface = None if mode == "top" else st.iface
                    err = handler(self, st, m)
                    if isinstance(err, tuple):
                        return err
                    if err:
                        return ("value_out_of_range", err)
                    return None
            mode = PARENT[mode]
        return ("not_allowed", f"perintah tidak termasuk pola yang diizinkan (mode {st.mode})")

    # ------------------------------------------------------------ registrasi pola

    def _on(self, modes: str, pattern: str):
        def deco(fn: Handler):
            for mode in modes.split():
                self.rules[mode].append((re.compile(pattern), fn))
            return fn
        return deco

    def _register(self) -> None:  # noqa: C901 - daftar aturan memang panjang
        on = self._on
        topo = self.topo

        def need_iface(st: _State, name: str):
            if not topo.has_interface(st.router, name):
                return ("unknown_interface", f"interface '{name}' tidak ada di router {st.router}")
            return None

        def need_neighbor(st: _State, ip: str):
            if ip not in topo.routers[st.router].bgp_neighbors:
                return ("unknown_neighbor", f"{ip} bukan neighbor BGP {st.router} di topologi")
            return None

        # ---------------- navigasi
        @on("top", r"(configure terminal|configure|conf t|conf)")
        def _conf(_, st, m):
            st.mode, st.iface = "top", None

        @on("top interface ospf bgp bgp_af route_map", r"end")
        def _end(_, st, m):
            st.mode, st.iface = "top", None

        @on("interface ospf bgp route_map", r"exit|quit")
        def _exit(_, st, m):
            st.mode, st.iface = "top", None

        @on("top", r"exit|quit")
        def _exit_top(_, st, m):
            pass

        @on("bgp_af", r"exit-address-family|exit|quit")
        def _exit_af(_, st, m):
            st.mode = "bgp"

        @on("top", r"(write|write memory|write file|copy running-config startup-config)")
        def _write(_, st, m):
            pass

        @on("top", r"interface (\S+)")
        def _iface(_, st, m):
            err = need_iface(st, m.group(1))
            if err:
                return err
            st.mode, st.iface = "interface", m.group(1)

        @on("top", r"router ospf")
        def _ospf(_, st, m):
            st.mode = "ospf"

        @on("top", r"router bgp (\d+)")
        def _bgp(_, st, m):
            asn = int(m.group(1))
            if asn != topo.routers[st.router].asn:
                return ("wrong_asn", f"router bgp {asn} tidak sesuai ASN {st.router} ({topo.routers[st.router].asn})")
            st.mode = "bgp"

        @on("bgp", r"address-family ipv4( unicast)?")
        def _af(_, st, m):
            st.mode = "bgp_af"

        # ---------------- shell: hanya ip link untuk MTU / up
        @on("shell", r"ip link set (?:dev )?(\S+) mtu (\d+)")
        def _shell_mtu(_, st, m):
            return need_iface(st, m.group(1)) or _mtu_value(int(m.group(2)))

        @on("shell", r"ip link set (?:dev )?(\S+) up")
        def _shell_up(_, st, m):
            return need_iface(st, m.group(1))

        def _mtu_value(v: int):
            if not _in(v, "mtu"):
                return f"MTU {v} di luar rentang wajar {LIMITS['mtu']}"
            return None

        # ---------------- interface
        @on("interface", r"(?:ip )?mtu (\d+)")
        def _mtu(_, st, m):
            return _mtu_value(int(m.group(1)))

        @on("interface", r"no shutdown")
        def _noshut(_, st, m):
            pass

        @on("interface", r"(no )?ip address (" + PFX_RE + r")")
        def _addr(_, st, m):
            try:
                addr = ipaddress.IPv4Interface(m.group(2))
            except ValueError:
                return f"alamat {m.group(2)} tidak valid"
            want = topo.interface(st.router, st.iface).ips
            if not want:
                return None
            shown = ", ".join(map(str, want))
            if m.group(1) and addr in want:
                return ("address_mismatch", f"menghapus alamat yang benar {addr} dari {st.router} {st.iface}")
            if not m.group(1) and addr not in want:
                return ("address_mismatch", f"alamat {addr} tidak sesuai topologi ({shown}) untuk {st.router} {st.iface}")
            return None

        def _timer(st: _State, kind: str, v: int):
            key = "hello" if kind == "hello" else "dead"
            if not _in(v, key):
                return f"{kind}-interval {v} di luar rentang wajar {LIMITS[key]}"
            t = st.timers.setdefault(st.iface, {})
            t[key] = v
            if "hello" in t and "dead" in t and t["dead"] <= t["hello"]:
                return f"dead-interval ({t['dead']}) harus lebih besar dari hello-interval ({t['hello']})"
            return None

        @on("interface", r"ip ospf (hello|dead)-interval (\d+)")
        def _ospf_timer(_, st, m):
            return _timer(st, m.group(1), int(m.group(2)))

        @on("interface", r"ip ospf dead-interval minimal hello-multiplier (\d+)")
        def _ospf_fast(_, st, m):
            v = int(m.group(1))
            return None if 1 <= v <= 10 else f"hello-multiplier {v} di luar rentang 1-10"

        @on("interface", r"no ip ospf (hello|dead)-interval( \d+)?")
        def _no_timer(_, st, m):
            pass

        @on("interface", r"(no )?ip ospf (cost|retransmit-interval|transmit-delay) ?(\d+)?")
        def _cost(_, st, m):
            if m.group(1) or m.group(3) is None:
                return None if m.group(1) else "nilai wajib diisi"
            key = "cost" if m.group(2) == "cost" else "retransmit"
            v = int(m.group(3))
            return None if _in(v, key) else f"{m.group(2)} {v} di luar rentang {LIMITS[key]}"

        @on("interface", r"ip ospf area (" + AREA_RE + r")")
        def _area(_, st, m):
            try:
                area = _norm_area(m.group(1))
            except ValueError:
                return f"area {m.group(1)} tidak valid"
            want = topo.interface(st.router, st.iface).ospf_area
            if want is None:
                return ("area_mismatch", f"{st.router} {st.iface} bukan link OSPF di topologi")
            if area != _norm_area(want):
                return ("area_mismatch", f"area {area} tidak sesuai topologi ({want}) untuk {st.router} {st.iface}")
            return None

        @on("interface", r"no ip ospf area( " + AREA_RE + r")?")
        def _no_area(_, st, m):
            pass

        @on("interface", r"(no )?ip ospf authentication( message-digest| null)?")
        def _auth(_, st, m):
            pass

        @on("interface", r"ip ospf message-digest-key (\d+) md5 (\S+)")
        def _md5(_, st, m):
            if not _in(int(m.group(1)), "md5_key_id"):
                return f"key-id {m.group(1)} di luar rentang 1-255"
            if len(m.group(2)) > 16:
                return "kunci MD5 OSPF maksimal 16 karakter"
            return None

        @on("interface", r"no ip ospf message-digest-key (\d+)( md5 \S+)?")
        def _no_md5(_, st, m):
            pass

        @on("interface", r"ip ospf authentication-key (\S+)")
        def _authkey(_, st, m):
            return None if len(m.group(1)) <= 8 else "authentication-key OSPF maksimal 8 karakter"

        @on("interface", r"no ip ospf authentication-key( \S+)?")
        def _no_authkey(_, st, m):
            pass

        @on("interface", r"(no )?ip ospf (mtu-ignore|passive)")
        def _misc(_, st, m):
            pass

        @on("interface", r"ip ospf network (point-to-point|broadcast)")
        def _net(_, st, m):
            pass

        @on("interface", r"no ip ospf network( point-to-point| broadcast)?")
        def _no_net(_, st, m):
            pass

        # ---------------- router ospf
        @on("ospf", r"(no )?network (" + PFX_RE + r") area (" + AREA_RE + r")")
        def _network(_, st, m):
            try:
                net = ipaddress.IPv4Network(m.group(2), strict=False)
                area = _norm_area(m.group(3))
            except ValueError:
                return "prefix atau area tidak valid"
            if m.group(1):
                return None
            for iface in topo.routers[st.router].interfaces.values():
                if iface.ip and iface.ip.ip in net and iface.ospf_area is not None:
                    if area != _norm_area(iface.ospf_area):
                        return ("area_mismatch", f"area {area} tidak sesuai topologi untuk {iface.name}")
                    return None
            return ("unknown_interface", f"tidak ada link OSPF {st.router} di dalam {net}")

        @on("ospf", r"no passive-interface (\S+)")
        def _no_passive(_, st, m):
            return need_iface(st, m.group(1))

        @on("ospf", r"passive-interface (lo|default)")
        def _passive_lo(_, st, m):
            if m.group(1) == "default":
                return ("not_allowed", "passive-interface default mematikan semua adjacency")
            return None

        @on("ospf", r"(no )?area (" + AREA_RE + r") authentication( message-digest)?")
        def _area_auth(_, st, m):
            pass

        @on("ospf", r"(no )?ospf router-id (" + IP_RE + r")")
        def _rid(_, st, m):
            want = topo.routers[st.router].router_id
            if not m.group(1) and want and m.group(2) != want:
                return f"router-id {m.group(2)} tidak sesuai topologi ({want})"
            return None

        # ---------------- router bgp (+ address-family)
        @on("bgp", r"neighbor (" + IP_RE + r") remote-as (\d+|internal|external)")
        def _remote_as(_, st, m):
            ip = m.group(1)
            err = need_neighbor(st, ip)
            if err:
                return err
            peer, peer_asn = topo.routers[st.router].bgp_neighbors[ip]
            v = m.group(2)
            my_asn = topo.routers[st.router].asn
            ok = (v == "internal" and peer_asn == my_asn) or (v == "external" and peer_asn != my_asn) \
                or (v.isdigit() and int(v) == peer_asn)
            if not ok:
                return ("wrong_asn", f"remote-as {v} tidak sesuai ASN {peer} ({peer_asn})")
            return None

        @on("bgp bgp_af", r"(no )?neighbor (" + IP_RE + r") (route-map|prefix-list) (" + NAME_RE + r") (in|out)")
        def _filter(_, st, m):
            return need_neighbor(st, m.group(2))

        @on("bgp bgp_af", r"(no )?neighbor (" + IP_RE + r") (activate|next-hop-self|soft-reconfiguration inbound)")
        def _nb_flag(_, st, m):
            return need_neighbor(st, m.group(2))

        @on("bgp", r"no neighbor (" + IP_RE + r") shutdown")
        def _nb_noshut(_, st, m):
            return need_neighbor(st, m.group(1))

        @on("bgp", r"(no )?neighbor (" + IP_RE + r") update-source (\S+)")
        def _upd(_, st, m):
            err = need_neighbor(st, m.group(2))
            if err or m.group(1):
                return err
            src = m.group(3)
            if _valid_ip(src):  # FRR menerima alamat sumber; harus milik router ini
                return None if topo.routers[st.router].owns_ip(src) else (
                    "unknown_interface", f"{src} bukan alamat milik {st.router}")
            return need_iface(st, src)

        @on("bgp", r"(no )?neighbor (" + IP_RE + r") ebgp-multihop( \d+)?")
        def _mh(_, st, m):
            err = need_neighbor(st, m.group(2))
            if err or not m.group(3):
                return err
            v = int(m.group(3))
            return None if _in(v, "multihop") else f"ebgp-multihop {v} di luar rentang 1-255"

        @on("bgp", r"neighbor (" + IP_RE + r") timers (\d+) (\d+)")
        def _nb_timers(_, st, m):
            err = need_neighbor(st, m.group(1))
            if err:
                return err
            k, h = int(m.group(2)), int(m.group(3))
            if not (_in(k, "bgp_keepalive") and _in(h, "bgp_hold")):
                return "timer BGP di luar rentang 0-65535"
            if h != 0 and (h < 3 or k >= h):
                return f"hold time ({h}) harus >= 3 dan lebih besar dari keepalive ({k})"
            return None

        @on("bgp", r"no neighbor (" + IP_RE + r") timers( \d+ \d+)?")
        def _no_nb_timers(_, st, m):
            return need_neighbor(st, m.group(1))

        @on("bgp", r"(no )?neighbor (" + IP_RE + r") password( \S+)?")
        def _pw(_, st, m):
            return need_neighbor(st, m.group(2))

        @on("bgp_af", r"(no )?network (" + PFX_RE + r")")
        def _bgp_net(_, st, m):
            try:
                net = ipaddress.IPv4Network(m.group(2), strict=True)
            except ValueError:
                return f"prefix {m.group(2)} tidak valid"
            if m.group(1):
                return None
            own = {i.network for itf in topo.routers[st.router].interfaces.values() for i in itf.ips}
            if own and net not in own:
                return ("address_mismatch", f"{net} bukan prefix milik {st.router}; tidak boleh diiklankan")
            return None

        # ---------------- prefix-list dan route-map (mode top)
        @on("top", r"ip prefix-list (" + NAME_RE + r")(?: seq (\d+))? (permit|deny) (" + PFX_RE + r"|any)"
                   r"(?: ge (\d+))?(?: le (\d+))?")
        def _pl(_, st, m):
            if m.group(2) and not _in(int(m.group(2)), "seq"):
                return "seq di luar rentang"
            if m.group(4) == "any":
                return None
            try:
                net = ipaddress.IPv4Network(m.group(4), strict=True)
            except ValueError:
                return f"prefix {m.group(4)} tidak valid (bit host harus 0)"
            ge = int(m.group(5)) if m.group(5) else None
            le = int(m.group(6)) if m.group(6) else None
            lo = net.prefixlen
            if ge is not None and not (lo < ge <= 32):
                return f"ge {ge} harus di antara {lo + 1} dan 32"
            if le is not None and not ((ge or lo) <= le <= 32):
                return f"le {le} harus di antara {ge or lo} dan 32"
            return None

        @on("top", r"no ip prefix-list (" + NAME_RE + r")( seq \d+.*)?")
        def _no_pl(_, st, m):
            pass

        @on("top", r"route-map (" + NAME_RE + r") (permit|deny) (\d+)")
        def _rm(_, st, m):
            if not _in(int(m.group(3)), "seq"):
                return "sequence route-map di luar rentang"
            st.mode = "route_map"

        @on("top", r"no route-map (" + NAME_RE + r")( (permit|deny) \d+)?")
        def _no_rm(_, st, m):
            pass

        @on("route_map", r"(no )?match ip address prefix-list (" + NAME_RE + r")")
        def _rm_match(_, st, m):
            pass

        @on("route_map", r"set (local-preference|metric) (\d+)")
        def _rm_set(_, st, m):
            key = "local_pref" if m.group(1) == "local-preference" else "metric"
            v = int(m.group(2))
            return None if _in(v, key) else f"{m.group(1)} {v} di luar rentang"

        @on("route_map", r"no set (local-preference|metric)( \d+)?")
        def _rm_noset(_, st, m):
            pass

        # ---------------- exec: soft reset sesi tertentu
        @on("top", r"clear (?:ip )?bgp (?:ipv4 unicast )?(" + IP_RE + r")( soft( in| out)?)?")
        def _clear(_, st, m):
            return need_neighbor(st, m.group(1))

        @on("top", r"show [a-z0-9 ./:\-]+")
        def _show(_, st, m):
            pass  # hanya baca, aman

        @on("top", r"clear ip ospf (?:interface )?(\S+)")
        def _clear_ospf_if(_, st, m):
            return need_iface(st, m.group(1))


# ------------------------------------------------------------------ CLI

def lint(commands, topology: Topology | None = None) -> dict:
    """Bentuk pemanggilan singkat untuk runner: lint(commands) -> {"passed", "violations"}."""
    return CommandLinter(topology or Topology.load()).lint(commands).to_dict()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Periksa perintah perbaikan sebelum dijalankan.")
    ap.add_argument("file", nargs="?", help="file JSON berisi daftar perintah atau jawaban agen (default: stdin)")
    ap.add_argument("--topology", type=Path, default=None)
    args = ap.parse_args(argv)
    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    data = json.loads(text)
    if isinstance(data, dict) and "commands" in data and "router" in data and "root_cause" in data:
        data = data["commands"]  # jawaban agen utuh
    result = lint(data, Topology.load(args.topology))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
