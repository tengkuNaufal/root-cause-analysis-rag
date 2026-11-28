"""Validasi input evaluasi offline; tidak mengakses API, model, atau lab."""
from __future__ import annotations

import hashlib
from pathlib import Path

from rca.catalog import catalog_path, load_catalog

ATTEMPT_POLICIES = ("reject", "first", "last")


def checked_catalog(runs: list[dict], path: Path | None = None):
    selected = Path(path or catalog_path())
    digest = hashlib.sha256(selected.read_bytes()).hexdigest()
    for run in runs:
        if run.get("catalog_sha256") is not None and run["catalog_sha256"] != digest:
            raise ValueError("catalog_sha256 does not match evaluator catalog")
    return load_catalog(selected), digest


def positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def identity(run):
    return {k: run.get(k) for k in ("plan_order", "fault_id", "variant", "trial", "attempt",
                                   "run_id", "request_id", "job_id")}


def select_attempts(runs: list[dict], policy: str = "reject"):
    """Satu cell = fault/variant/trial. Tidak menebak attempt dari urutan berkas."""
    if policy not in ATTEMPT_POLICIES:
        raise ValueError(f"Unknown attempt policy: {policy}")
    cells, orders = {}, {}
    for run in runs:
        if not run.get("fault_id") or not run.get("variant") or not positive_int(run.get("trial")):
            raise ValueError("Each run needs fault_id, variant and a positive integer trial")
        key = (str(run["fault_id"]), str(run["variant"]), run["trial"])
        order = run.get("plan_order")
        if order is not None:
            if not positive_int(order) or (order in orders and orders[order] != key):
                raise ValueError("Conflicting or invalid plan_order")
            orders[order] = key
        if run.get("attempt") is not None and not positive_int(run["attempt"]):
            raise ValueError("attempt must be a positive integer")
        cells.setdefault(key, []).append(run)
    selected, excluded = [], []
    for key, group in cells.items():
        if len({r["plan_order"] for r in group if r.get("plan_order") is not None}) > 1:
            raise ValueError(f"Multiple plan_order values for cell {key}; separate benchmark sessions")
        if len(group) == 1:
            selected.append(group[0])
            continue
        if policy == "reject":
            raise ValueError(f"Duplicate scheduled cell {key}; choose --attempt-policy first or last explicitly")
        attempts = [r.get("attempt") for r in group]
        if any(a is None for a in attempts) or len(set(attempts)) != len(attempts):
            raise ValueError(f"Ambiguous attempts for cell {key}; separate duplicate/session data")
        chosen = (min if policy == "first" else max)(group, key=lambda r: r["attempt"])
        selected.append(chosen)
        excluded.extend(identity(r) for r in group if r is not chosen)
    audit = {"attempt_policy": policy, "input_rows": len(runs), "selected_rows": len(selected),
             "excluded_rows": len(excluded), "excluded": excluded}
    return selected, audit
