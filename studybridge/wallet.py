"""Sandbox multi-currency wallet. No real money moves anywhere."""
import copy
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .fx import quote
from .money import D, convert_mid, norm_ccy, q
from .remittance import evaluate, provider_by_id
from .security.audit import mask_account


class WalletError(Exception):
    pass


class SandboxWallet:
    def __init__(self, profile: dict):
        self.profile = copy.deepcopy(profile)
        self.owner = profile["owner"]
        self.balances = {norm_ccy(c): D(v) for c, v in profile["balances"].items()}
        self.beneficiaries = {b["id"]: b for b in profile.get("beneficiaries", [])}
        self.transactions = list(profile.get("transactions", []))
        self._processed = {}

    @classmethod
    def from_file(cls, path) -> "SandboxWallet":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def total_value(self, home: str = "BDT") -> Decimal:
        return sum((convert_mid(v, c, home) for c, v in self.balances.items()), Decimal(0))

    def overview(self, home: str = "BDT") -> dict:
        return {
            "owner": self.owner["display_name"],
            "balances": {c: q(v) for c, v in self.balances.items()},
            "total_value_home": q(self.total_value(home)),
            "home_currency": home,
            "beneficiaries": [
                {"id": b["id"], "name": b["name"], "currency": b["currency"],
                 "account": mask_account(b["account_number"])}
                for b in self.beneficiaries.values()
            ],
        }

    def _debit(self, ccy: str, amount: Decimal):
        if self.balances.get(ccy, Decimal(0)) < amount:
            raise WalletError(f"insufficient {ccy} balance")
        self.balances[ccy] -= amount

    def convert(self, amount, src: str, dst: str, idempotency_key: str) -> dict:
        if idempotency_key in self._processed:
            return {**self._processed[idempotency_key], "replayed": True}
        qt = quote(amount, src, dst)
        self._debit(qt["from"], D(amount))
        self.balances[qt["to"]] = self.balances.get(qt["to"], Decimal(0)) + qt["you_get"]
        rec = {"type": "convert", "at": datetime.now().isoformat(timespec="seconds"),
               "debited": q(amount), "debit_currency": qt["from"],
               "credited": qt["you_get"], "credit_currency": qt["to"], "rate": qt["applied_rate"]}
        self._processed[idempotency_key] = rec
        return rec

    def send(self, beneficiary_id: str, amount, src: str, provider_id: str, idempotency_key: str) -> dict:
        if idempotency_key in self._processed:
            return {**self._processed[idempotency_key], "replayed": True}
        b = self.beneficiaries.get(beneficiary_id)
        if b is None:
            raise WalletError("beneficiary is not in the saved list")
        src = norm_ccy(src)
        opt = evaluate(provider_by_id(provider_id), amount, src, b["currency"])
        if not opt["eligible"]:
            raise WalletError("provider not eligible: " + "; ".join(opt["reasons"]))
        self._debit(src, D(amount))
        rec = {"type": "send", "at": datetime.now().isoformat(timespec="seconds"),
               "beneficiary": b["name"], "account": mask_account(b["account_number"]),
               "debited": q(amount), "debit_currency": src, "provider": opt["provider"],
               "fee": opt["fee"], "recipient_gets": opt["recipient_gets"],
               "recipient_currency": b["currency"], "status": "SANDBOX_SETTLED",
               "sandbox_reference": "SBX-" + idempotency_key[:10].upper()}
        self._processed[idempotency_key] = rec
        return rec
