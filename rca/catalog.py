"""Memuat katalog fault (ground truth). Hanya dibaca runner dan evaluator, tidak pernah dikirim ke agen.

Default: faults/host1.yaml (katalog Host 1). Ganti lewat argumen atau RCA_CATALOG.
Perintah perbaikan yang benar diambil dari `fix` bila ada, selain itu dari `revert`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
HOST1_CATALOG = ROOT / "faults" / "host1.yaml"
SAMPLE_CATALOG = ROOT / "data" / "catalog.sample.yaml"


@dataclass
class Fault:
    id: str
    fault_class: str
    router: str
    interface: str | None = None
    neighbor: str | None = None
    fix: list[dict] = field(default_factory=list)
    inject: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def catalog_path() -> Path:
    env = os.environ.get("RCA_CATALOG")
    if env:
        return Path(env)
    return HOST1_CATALOG if HOST1_CATALOG.exists() else SAMPLE_CATALOG


def _as_list(x) -> list[dict]:
    if not x:
        return []
    return x if isinstance(x, list) else [x]


def load_catalog(path: str | Path | None = None) -> dict[str, Fault]:
    with open(path or catalog_path(), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    items = data["faults"] if isinstance(data, dict) and "faults" in data else data
    faults: dict[str, Fault] = {}
    for item in items:
        target = item.get("target") or {}
        gt = item.get("ground_truth") or {}
        fault = Fault(
            id=str(item["id"]),
            fault_class=item.get("class") or item.get("kind") or gt.get("class"),
            router=item.get("router") or gt.get("router") or target.get("router"),
            interface=item.get("interface") or gt.get("interface") or target.get("interface"),
            neighbor=item.get("neighbor") or gt.get("neighbor") or target.get("neighbor"),
            fix=_as_list(item.get("fix") or item.get("remediation") or item.get("revert")),
            inject=_as_list(item.get("inject")),
            raw=item,
        )
        faults[fault.id] = fault
    return faults
