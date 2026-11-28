"""Baca evidence arsip lokal untuk rubrik; tidak melakukan fetch atau import runtime live."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

BINDINGS = ("id", "kind", "source_id", "source_sha256", "locator")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def contained(root, child):
    path = (root / child).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Evidence archive path escapes its directory")
    return path


def bundle(run: dict, used: list[str], archive: Path | None):
    """Return anonymous cited fragments and private source hashes. All validation precedes output."""
    if not used:
        return [], []
    diag = run.get("diagnosis") or {}
    manifest = diag.get("evidence") or []
    by_id = {e["id"]: e for e in manifest}
    if len(by_id) != len(manifest) or not set(used) <= set(by_id):
        raise ValueError("Cited evidence missing or duplicated in manifest")
    local_rule = diag.get("mode") == "local" and diag.get("variant") == "rule_based"
    refs, directory = {}, None
    if not local_rule:
        jid = diag.get("job_id")
        if archive is None or not isinstance(jid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", jid):
            raise ValueError("Cited live evidence needs --evidence-root and a valid job_id")
        directory = contained(Path(archive), jid)
        index = json.loads(contained(directory, "evidence-index.json").read_text(encoding="utf-8"))
        refs = {r["payload"]["id"]: r for r in index}
        if len(refs) != len(index):
            raise ValueError("Duplicate evidence archive references")
    public, audit = [], []
    for eid in sorted(set(used)):
        expected = by_id[eid]
        if local_rule:
            content = expected.get("excerpt")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Rule evidence excerpt missing")
            source_sha = None  # Bound to source JSONL hash instead of claiming an upstream source hash.
        else:
            if eid not in refs:
                raise ValueError(f"Archived evidence missing: {eid}")
            ref = refs[eid]
            payload = ref["payload"]
            if any(payload.get(k) != expected.get(k) for k in BINDINGS):
                raise ValueError(f"Evidence manifest binding mismatch: {eid}")
            raw = contained(directory, ref["file"]).read_bytes()
            source_sha = digest(raw)
            if source_sha != expected.get("source_sha256") or expected.get("source_id") != "sha256:" + source_sha:
                raise ValueError(f"Evidence source hash mismatch: {eid}")
            fragment = json.loads(raw)
            pointer = expected["locator"]
            if pointer and not pointer.startswith("/"):
                raise ValueError("Invalid evidence JSON pointer")
            # Existing live root locator '/' means the complete source object.
            for token in pointer.split("/")[1:] if pointer not in ("", "/") else []:
                token = token.replace("~1", "/").replace("~0", "~")
                fragment = fragment[int(token)] if isinstance(fragment, list) else fragment[token]
            content = canonical(fragment)
            if content != payload.get("content"):
                raise ValueError(f"Evidence fragment mismatch: {eid}")
        public.append({"id": eid, "kind": expected["kind"], "content": content})
        audit.append({"id": eid, "source_sha256": source_sha, "content_sha256": digest(content.encode("utf-8"))})
    return public, audit
