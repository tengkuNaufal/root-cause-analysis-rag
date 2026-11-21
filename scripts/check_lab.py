#!/usr/bin/env python3
# Mengecek interface, OSPF, BGP, dan ping antar-router di lab FRR, lalu nyimpen snapshot JSON-nya.
# Exit code 1 kalau ada cek yang gagal, jadi bisa dipakai di skrip lain.
import argparse
import itertools
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN_PLAN = ROOT / "lab" / "host1" / "frr" / "design-plan.json"
EXPECTED_MTU = 1500


# Menyusun kondisi normal lab rca dari design-plan.json, biar gak ada dua sumber topologi Host 1.
# Alamat ping-nya pakai prefix service 10.100.N.1 karena r5/r6 gak punya rute ke loopback 10.255.0.N.
def from_design_plan(path):
    plan = json.loads(path.read_text())
    nodes = {n["name"]: n for n in plan["nodes"]}
    exp = {name: {"addr": n["service"].split("/")[0], "ifaces": [], "ospf": [], "bgp": []}
           for name, n in nodes.items()}
    for link in plan["links"]:
        a, b = link["endpoints"]
        for me, other in ((a, b), (b, a)):
            exp[me["router"]]["ifaces"].append(me["interface"])
            if link["protocol"] == "ospf":
                exp[me["router"]]["ospf"].append(nodes[other["router"]]["router_id"])
            else:
                exp[me["router"]]["bgp"].append(other["ipv4"].split("/")[0])
    for x, y in plan["ibgp_pairs"]:
        exp[x]["bgp"].append(nodes[y]["router_id"])
        exp[y]["bgp"].append(nodes[x]["router_id"])
    return exp


# Menyimpan kondisi normal lab replika: alamat ping, interface data, tetangga OSPF (router-id), peer eBGP.
EXPECTED = {
    "lab2": {
        "r1": {"addr": "10.255.0.1", "ifaces": ["eth1"], "ospf": ["10.255.0.2"], "bgp": []},
        "r2": {"addr": "10.255.0.2", "ifaces": ["eth1"], "ospf": ["10.255.0.1"], "bgp": []},
    },
    "topik8": {
        "r1": {"addr": "10.255.0.1", "ifaces": ["eth1"], "ospf": ["10.255.0.2"], "bgp": []},
        "r2": {"addr": "10.255.0.2", "ifaces": ["eth1", "eth2", "eth3"], "ospf": ["10.255.0.1"],
               "bgp": ["10.0.24.2", "10.0.26.1"]},
        "r3": {"addr": "10.255.0.3", "ifaces": ["eth1"], "ospf": ["10.255.0.4"], "bgp": []},
        "r4": {"addr": "10.255.0.4", "ifaces": ["eth1", "eth2", "eth3"], "ospf": ["10.255.0.3"],
               "bgp": ["10.0.24.1", "10.0.46.2"]},
        "r5": {"addr": "10.255.0.5", "ifaces": ["eth1"], "ospf": ["10.255.0.6"], "bgp": []},
        "r6": {"addr": "10.255.0.6", "ifaces": ["eth1", "eth2", "eth3"], "ospf": ["10.255.0.5"],
               "bgp": ["10.0.46.1", "10.0.26.2"]},
    },
}
if DESIGN_PLAN.exists():
    EXPECTED["rca"] = from_design_plan(DESIGN_PLAN)


def run(container, *cmd):
    p = subprocess.run(["docker", "exec", container, *cmd], capture_output=True, text=True, timeout=20)
    return p.returncode, p.stdout, p.stderr


def vtysh_json(container, command):
    code, out, err = run(container, "vtysh", "-c", command)
    if code != 0:
        raise RuntimeError(f"{container}: '{command}' gagal: {err.strip()}")
    return json.loads(out or "{}")


def check(lab):
    expected = EXPECTED[lab]
    snapshot = {"lab": lab, "taken_at_utc": datetime.now(timezone.utc).isoformat(), "routers": {}, "ping": {}}
    failures = []

    for r, exp in expected.items():
        c = f"clab-{lab}-{r}"
        _, link_out, _ = run(c, "ip", "-j", "link", "show")
        links = {l["ifname"]: l for l in json.loads(link_out or "[]")}
        # Melewati query OSPF di router yang gak jalanin ospfd (r5/r6 di lab rca).
        ospf = vtysh_json(c, "show ip ospf neighbor json").get("neighbors", {}) if exp["ospf"] else {}
        bgp = vtysh_json(c, "show bgp summary json").get("ipv4Unicast", {}).get("peers", {})
        routes = vtysh_json(c, "show ip route json")
        snapshot["routers"][r] = {"links": links, "ospf_neighbors": ospf, "bgp_peers": bgp, "routes": routes}

        for ifc in exp["ifaces"]:
            l = links.get(ifc)
            if l is None:
                failures.append(f"{r} {ifc}: interface tidak ada")
                continue
            if "UP" not in l.get("flags", []):
                failures.append(f"{r} {ifc}: interface down")
            if l.get("mtu") != EXPECTED_MTU:
                failures.append(f"{r} {ifc}: MTU {l.get('mtu')} (harapan {EXPECTED_MTU})")

        for nbr in exp["ospf"]:
            states = [e.get("converged") for e in ospf.get(nbr, [])]
            if "Full" not in states:
                failures.append(f"{r}: OSPF ke {nbr} tidak Full ({states or 'tidak ada'})")

        for peer in exp["bgp"]:
            state = bgp.get(peer, {}).get("state", "tidak ada")
            if state != "Established":
                failures.append(f"{r}: BGP ke {peer} {state}")

    for src, dst in itertools.permutations(expected, 2):
        a, b = expected[src]["addr"], expected[dst]["addr"]
        code, _, _ = run(f"clab-{lab}-{src}", "ping", "-c", "1", "-W", "1", "-I", a, b)
        snapshot["ping"][f"{src}->{dst}"] = code == 0
        if code != 0:
            failures.append(f"ping {src} ({a}) -> {dst} ({b}) gagal")

    snapshot["failures"] = failures
    return snapshot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", choices=sorted(EXPECTED), default="rca")
    ap.add_argument("--out", default="data/snapshots", help="folder penyimpanan snapshot JSON")
    args = ap.parse_args()

    snap = check(args.lab)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = snap["taken_at_utc"].replace(":", "").replace("-", "")[:15]
    path = out_dir / f"{args.lab}_{stamp}Z.json"
    path.write_text(json.dumps(snap, indent=2))

    ok_pings = sum(snap["ping"].values())
    print(f"Lab {args.lab}: {len(snap['routers'])} router, ping {ok_pings}/{len(snap['ping'])} berhasil")
    if snap["failures"]:
        print("GAGAL:")
        for f in snap["failures"]:
            print("  -", f)
    else:
        print("SEMUA CEK LOLOS")
    print(f"Snapshot: {path}")
    sys.exit(1 if snap["failures"] else 0)


if __name__ == "__main__":
    main()
