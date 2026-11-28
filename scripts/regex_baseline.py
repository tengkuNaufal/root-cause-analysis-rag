#!/usr/bin/env python3
# Pembanding regex (varian rule_based): diagnosis cuma pakai pola teks dari log FRR dan output show,
# tanpa model dan tanpa melihat katalog atau ground truth. Hasilnya dibentuk seperti job API live
# supaya runner, linter, executor, dan evaluator memperlakukannya sama dengan varian lain.
#
#   python3 scripts/regex_baseline.py            # ambil teks dari lab sekarang lalu tampilkan diagnosisnya
import ipaddress
import json
import re
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fault_runner as fr  # noqa: E402
import live_client as lc  # noqa: E402

VARIANT = "rule_based"
RULES_VERSION = "regex-v1"
LOG_LINES = 400

# Sumber teks per router. Nilai default (MTU 1500, hello 1, area 0) dianggap pengetahuan operator
# soal standar lab, bukan bocoran fault tertentu.
SOURCES = {
    "link": "ip -o link show",
    "addr": "ip -o -4 addr show",
    "ospf_neighbor": "vtysh -c 'show ip ospf neighbor'",
    "ospf_interface": "vtysh -c 'show ip ospf interface'",
    "bgp_summary": "vtysh -c 'show bgp ipv4 unicast summary'",
    "bgp_table": "vtysh -c 'show bgp ipv4 unicast'",
    "bgp_config": "vtysh -c 'show running-config bgpd'",
    "log": f"tail -n {LOG_LINES} /var/log/frr/events.log",
}
STANDARD_MTU = 1500
LOG_TIME = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})")
SEP = "@@regex@@"


# Mengambil semua teks satu router dalam satu docker exec biar diagnosis gak lama nunggu antrean Docker.
def collect(routers, since_utc=None):
    def one(router):
        script = f"; echo {SEP}; ".join(f"{cmd} 2>&1" for cmd in SOURCES.values())
        try:
            parts = subprocess.run(["docker", "exec", fr.container(router), "sh", "-c", script],
                                   capture_output=True, text=True, timeout=30).stdout.split(SEP)
        except subprocess.TimeoutExpired:
            parts = []
        if len(parts) != len(SOURCES):
            parts = ["% gagal mengambil teks"] * len(SOURCES)
        out = {name: text.strip("\n") for name, text in zip(SOURCES, parts)}
        if since_utc:
            out["log"] = recent_log(out["log"], since_utc)
        return router, out

    with ThreadPoolExecutor(len(routers)) as pool:
        return dict(pool.map(one, routers))


# Menyisakan baris log sejak fault di-inject biar kejadian dari run sebelumnya gak ikut kebaca.
def recent_log(text, since_utc):
    since = datetime.fromisoformat(since_utc.replace("Z", "+00:00")).strftime("%Y/%m/%d %H:%M:%S")
    keep = []
    for line in text.splitlines():
        m = LOG_TIME.match(line)
        if m and m.group(1) >= since:
            keep.append(line)
    return "\n".join(keep)


LINK = re.compile(r"^\d+: (eth\d+)(?:@\S+)?: <([^>]*)> mtu (\d+)", re.M)
ADDR = re.compile(r"^\d+: (\S+)\s+inet (\d+\.\d+\.\d+\.\d+/\d+)", re.M)
OSPF_IF = re.compile(r"^(\S+) is (?:up|down)\n(.*?)(?=^\S+ is (?:up|down)\n|\Z)", re.M | re.S)
LOCAL_AS = re.compile(r"local AS number (\d+)")
REMOTE_AS = re.compile(r"^ neighbor (\S+) remote-as (\d+)", re.M)
RMAP = re.compile(r"^route-map (\S+) (permit|deny) (\d+)", re.M)
RMAP_IN = re.compile(r"^\s+neighbor (\S+) route-map (\S+) in", re.M)
BAD_AS = re.compile(r"sent to neighbor (\S+) 2/2 \(OPEN Message Error/Bad Peer AS\)")
SERVICE_NET = ipaddress.ip_network("10.100.0.0/16")


def line_of(text, needle):
    for i, line in enumerate(text.splitlines()):
        if needle in line:
            return i, line.strip()
    return 0, needle


class Finding:
    def __init__(self, cls, router, commands, explanation):
        self.cls, self.router, self.commands, self.explanation = cls, router, commands, explanation
        self.evidence = []

    def cite(self, snap, router, source, needle):
        idx, line = line_of(snap[router][source], needle)
        self.evidence.append({"router": router, "source": source, "line": idx, "text": line[:300]})
        return self


def vtysh(router, lines):
    return {"router": router, "interpreter": "vtysh", "args": ["conf t", *lines]}


def ospf_ifaces(snap):
    out = []
    for router, src in snap.items():
        for m in OSPF_IF.finditer(src["ospf_interface"]):
            ifc, body = m.group(1), m.group(2)
            if ifc == "lo" or "Passive interface" in body:
                continue
            area = re.search(r"Area (\d+\.\d+\.\d+\.\d+)", body)
            hello = re.search(r"Timer intervals configured, Hello (\d+)s", body)
            auth = re.search(r"(Cryptographic|Simple password) authentication enabled", body)
            out.append({"router": router, "ifc": ifc, "area": area and area.group(1),
                        "hello": hello and hello.group(1), "auth": auth and auth.group(0)})
    return out


# Mengambil nilai paling umum di lab. None ikut dihitung, jadi auth yang cuma nyala di satu interface
# kebaca sebagai penyimpangan dari mayoritas yang gak pakai auth.
def majority(values):
    return max(set(values), key=values.count) if values else None


def addresses(snap):
    out = []
    for router, src in snap.items():
        for ifc, cidr in ADDR.findall(src["addr"]):
            out.append((router, ifc, ipaddress.ip_interface(cidr)))
    return out


def owner_of(snap, ip):
    for router, _, iface in addresses(snap):
        if str(iface.ip) == ip:
            return router
    return None


# Aturan diurutkan dari penyebab paling bawah (link) ke atas (BGP), soalnya fault di bawah biasanya
# ikut bikin gejala di atasnya. Aturan pertama yang cocok dipakai sebagai diagnosis.
def rule_link_down(snap):
    for router, src in snap.items():
        for ifc, flags, _ in LINK.findall(src["link"]):
            if ifc != "eth0" and "UP" not in flags.split(","):
                return Finding("link_down", router, [{"router": router, "interpreter": "ip",
                                                      "args": ["link", "set", ifc, "up"]}],
                               f"{ifc} di {router} administratively down").cite(snap, router, "link", f"{ifc}@")


def rule_mtu(snap):
    for router, src in snap.items():
        for ifc, _, mtu in LINK.findall(src["link"]):
            if ifc != "eth0" and int(mtu) != STANDARD_MTU:
                f = Finding("mtu_mismatch", router, [{"router": router, "interpreter": "ip",
                                                      "args": ["link", "set", ifc, "mtu", str(STANDARD_MTU)]}],
                            f"MTU {ifc} di {router} {mtu}, standar lab {STANDARD_MTU}")
                f.cite(snap, router, "link", f"{ifc}@")
                if "is larger than" in src["log"]:
                    f.cite(snap, router, "log", "is larger than")
                return f


def rule_wrong_ip(snap):
    links = [(r, ifc, i) for r, ifc, i in addresses(snap) if ifc.startswith("eth") and ifc != "eth0"]
    count = {}
    for _, _, i in links:
        count[i.network] = count.get(i.network, 0) + 1
    single = [x for x in links if count[x[2].network] == 1]
    if len(single) != 2:
        return None
    # Menentukan sisi yang salah: neighbor BGP-nya gak ada di subnet yang terhubung, atau OSPF-nya
    # mutus adjacency sendiri (KillNbr) di interface itu.
    def suspicious(x):
        router, ifc, _ = x
        src = snap[router]
        connected = [i.network for r, _, i in links if r == router]
        for nbr, _ in REMOTE_AS.findall(src["bgp_config"]):
            ip = ipaddress.ip_address(nbr)
            if not ip.is_private or str(ip).startswith("10.255."):
                continue
            if not any(ip in n for n in connected):
                return 2
        return 1 if re.search(rf"on {ifc}:\S+: Full -> Deleted \(KillNbr\)", src["log"]) else 0
    wrong, peer = sorted(single, key=suspicious, reverse=True)
    router, ifc, bad = wrong
    hosts = [h for h in peer[2].network.hosts() if h != peer[2].ip]
    if not hosts:
        return None
    good = f"{hosts[0]}/{peer[2].network.prefixlen}"
    f = Finding("wrong_ip_address", router, [vtysh(router, [f"interface {ifc}", f"no ip address {bad}",
                                                            f"ip address {good}"])],
                f"{ifc} di {router} pakai {bad}, gak satu subnet dengan {peer[0]} {peer[1]} {peer[2]}")
    return f.cite(snap, router, "addr", str(bad)).cite(snap, peer[0], "addr", str(peer[2]))


def ospf_rule(cls, key, fix):
    def rule(snap):
        ifaces = ospf_ifaces(snap)
        norm = majority([i[key] for i in ifaces])
        for i in ifaces:
            if i[key] != norm:
                f = Finding(cls, i["router"], [vtysh(i["router"], [f"interface {i['ifc']}", *fix(i, norm)])],
                            f"{key} OSPF {i['ifc']} di {i['router']} {i[key]}, interface lain {norm}")
                return f.cite(snap, i["router"], "ospf_interface", f"{i['ifc']} is")
    return rule


rule_hello = ospf_rule("ospf_hello_mismatch", "hello", lambda i, n: [f"ip ospf hello-interval {n}"])
rule_area = ospf_rule("ospf_area_mismatch", "area",
                      lambda i, n: [f"no ip ospf area {i['area']}", f"ip ospf area {n}"])
rule_auth = ospf_rule("ospf_auth_mismatch", "auth",
                      lambda i, n: ["no ip ospf message-digest-key 1", "no ip ospf authentication"])


def rule_bgp_shutdown(snap):
    for router, src in snap.items():
        for line in src["bgp_summary"].splitlines():
            if "Idle (Admin)" in line:
                nbr, asn = line.split()[0], LOCAL_AS.search(src["bgp_summary"]).group(1)
                f = Finding("bgp_neighbor_shutdown", router, [vtysh(router, [f"router bgp {asn}",
                                                                              f"no neighbor {nbr} shutdown"])],
                            f"neighbor {nbr} di {router} shutdown administratif")
                return f.cite(snap, router, "bgp_summary", "Idle (Admin)")


def rule_remote_as(snap):
    local = {r: (LOCAL_AS.search(s["bgp_summary"]) or [None, None])[1] for r, s in snap.items()}
    for router, src in snap.items():
        for nbr, asn in REMOTE_AS.findall(src["bgp_config"]):
            peer = owner_of(snap, nbr)
            if peer and local.get(peer) and asn != local[peer]:
                fix = [f"router bgp {local[router]}", f"neighbor {nbr} remote-as {local[peer]}"]
                f = Finding("bgp_wrong_remote_as", router, [vtysh(router, fix)],
                            f"{router} set remote-as {asn} untuk {nbr}, padahal {peer} AS {local[peer]}")
                f.cite(snap, router, "bgp_config", f"neighbor {nbr} remote-as {asn}")
                if BAD_AS.search(src["log"]):
                    f.cite(snap, router, "log", "Bad Peer AS")
                return f


def rule_inbound_filter(snap):
    for router, src in snap.items():
        cfg = src["bgp_config"]
        for nbr, rmap in RMAP_IN.findall(cfg):
            entries = [(int(seq), act) for name, act, seq in RMAP.findall(cfg) if name == rmap]
            last = max(seq for seq, _ in entries) if entries else None
            for seq, act in sorted(entries):
                if act == "deny" and seq != last:
                    f = Finding("bgp_inbound_filter", router, [vtysh(router, [f"no route-map {rmap} deny {seq}"])],
                                f"route-map {rmap} (inbound dari {nbr}) di {router} punya deny {seq} sebelum permit")
                    return f.cite(snap, router, "bgp_config", f"route-map {rmap} deny {seq}")


def rule_missing_network(snap):
    for router, src in snap.items():
        for ifc, cidr in ADDR.findall(src["addr"]):
            iface = ipaddress.ip_interface(cidr)
            if ifc == "lo" and iface.ip in SERVICE_NET and f"{iface.network}" not in src["bgp_table"]:
                asn = LOCAL_AS.search(src["bgp_summary"]).group(1)
                f = Finding("bgp_missing_network", router,
                            [vtysh(router, [f"router bgp {asn}", "address-family ipv4 unicast",
                                            f"network {iface.network}"])],
                            f"prefix layanan {iface.network} di {router} gak ada di tabel BGP-nya sendiri")
                return f.cite(snap, router, "addr", str(iface.network)).cite(snap, router, "bgp_table", "Network")


RULES = [rule_link_down, rule_mtu, rule_wrong_ip, rule_hello, rule_area, rule_auth, rule_bgp_shutdown,
         rule_remote_as, rule_inbound_filter, rule_missing_network]


def diagnose(snap):
    for rule in RULES:
        try:
            found = rule(snap)
        except (AttributeError, ValueError, KeyError):
            found = None  # output router gak lengkap (misalnya vtysh gagal), aturan ini dilewati aja
        if found:
            return found
    return None


# Membungkus hasil aturan jadi job berbentuk sama dengan API live. Evidence di manifest adalah baris
# teks yang dikutip aturan, jadi evaluator bisa ngecek ID evidence-nya juga.
def make_job(request, snap):
    found = diagnose(snap)
    job_id = f"rule-{uuid.uuid4()}"
    evidence = [{"id": f"e{i + 1}", "kind": "log" if e["source"] == "log" else "cli_output",
                 "source_id": f"{e['router']}:{e['source']}", "locator": f"line:{e['line']}", "excerpt": e["text"]}
                for i, e in enumerate(found.evidence if found else [])]
    ids = [e["id"] for e in evidence]
    assessment = {"router": found.router if found else None, "root_cause": found.cls if found else "unknown",
                  "confidence": None, "evidence_ids": ids, "commands": found.commands if found else [],
                  "explanation": found.explanation if found else "Gak ada pola yang cocok, diagnosis abstain."}
    result = {"request_id": request["request_id"], "status": "hypothesis" if found else "abstain",
              "root_cause_class": assessment["root_cause"] if found else None,
              "root_cause_router": assessment["router"]}
    now = lc.utc_now()
    return {"contract_version": lc.CONTRACT, "request_id": request["request_id"], "job_id": job_id,
            "mode": "local", "lab": request["lab"], "variant": request["variant"], "received_at": now,
            "updated_at": now, "execution_allowed": False, "simulation": False, "state": "completed",
            "result": result, "assessment": assessment, "evidence": evidence,
            "provenance": {"engine": "scripts/regex_baseline.py", "rules_version": RULES_VERSION,
                           "sources": sorted(SOURCES)}}


def main():
    fr.load_catalog(fr.ROOT / "faults" / "host1.yaml")
    snap = collect(sorted(fr.EXPECTED[fr.LAB]))
    found = diagnose(snap)
    if not found:
        print("Gak ada pola yang cocok (abstain)")
        return
    print(f"{found.cls} di {found.router}: {found.explanation}")
    for e in found.evidence:
        print(f"  [{e['router']} {e['source']}] {e['text']}")
    print(json.dumps(found.commands, indent=1))


if __name__ == "__main__":
    main()
