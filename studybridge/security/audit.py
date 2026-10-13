"""Tamper-evident audit log.

Each line is a JSON record whose `hash` is SHA-256 over the previous record's
hash plus this record's canonical JSON. Editing, deleting or reordering any
line breaks every hash after it, which verify() detects.
"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

GENESIS = "0" * 64
_SENSITIVE_KEYS = {"account_number", "account", "passport", "student_id", "phone", "email"}
_LONG_DIGITS = re.compile(r"\b\d{8,}\b")


def mask_account(value) -> str:
    s = str(value)
    return "****" + s[-4:] if len(s) > 4 else "****"


def _mask(obj):
    if isinstance(obj, dict):
        return {k: (mask_account(v) if k in _SENSITIVE_KEYS and not str(v).startswith("****") else _mask(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask(v) for v in obj]
    if isinstance(obj, str):
        return _LONG_DIGITS.sub(lambda m: mask_account(m.group()), obj)
    return obj


def _canonical(record: dict) -> str:
    return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


class AuditLog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last = GENESIS
        self._seq = 0
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self._last, self._seq = rec["hash"], rec["seq"]

    def append(self, event: str, data: dict) -> dict:
        self._seq += 1
        body = {"seq": self._seq, "ts": datetime.now().isoformat(timespec="seconds"),
                "event": event, "data": _mask(data), "prev_hash": self._last}
        body["hash"] = hashlib.sha256((self._last + _canonical(body)).encode()).hexdigest()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(_canonical(body) + "\n")
        self._last = body["hash"]
        return body

    def verify(self) -> dict:
        prev = GENESIS
        n = 0
        if not self.path.exists():
            return {"ok": True, "records": 0, "broken_at": None}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            n += 1
            stored = rec.pop("hash")
            expected = hashlib.sha256((prev + _canonical(rec)).encode()).hexdigest()
            if rec.get("prev_hash") != prev or stored != expected:
                return {"ok": False, "records": n, "broken_at": rec.get("seq")}
            prev = stored
        return {"ok": True, "records": n, "broken_at": None}
