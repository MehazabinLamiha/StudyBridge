"""Remittance provider comparison.

For each provider the recipient amount is computed in closed form:

    fee        = fixed_fee (converted to the source currency) + pct_fee * amount
    rate       = mid_rate * (1 - fx_margin)
    recipient  = (amount - fee) * rate
    total cost = (amount * mid_rate - recipient) / (amount * mid_rate)

The total cost therefore captures both the visible fee and the hidden FX
mark-up, which is what students usually miss when comparing services.
"""
from decimal import Decimal

from .config import PROVIDERS
from .money import D, RATE_Q, convert_mid, mid_rate, norm_ccy, q, to_usd


def provider_by_id(provider_id: str) -> dict:
    for p in PROVIDERS:
        if p["id"] == provider_id:
            return p
    raise ValueError(f"unknown provider: {provider_id!r}")


def _fixed_fee_src(p: dict, src: str) -> Decimal:
    return convert_mid(p["fixed_fee_usd"], "USD", src)


def evaluate(p: dict, amount, src: str, dst: str, deadline_days=None) -> dict:
    src, dst = norm_ccy(src), norm_ccy(dst)
    amount = D(amount)
    mid = mid_rate(src, dst)
    fee = _fixed_fee_src(p, src) + p["pct_fee"] * amount
    net = amount - fee
    rate = mid * (1 - p["fx_margin"])
    recipient = net * rate if net > 0 else Decimal(0)
    benchmark = amount * mid
    cost_pct = (benchmark - recipient) / benchmark * 100 if benchmark > 0 else Decimal(0)

    reasons = []
    usd = to_usd(amount, src)
    if p["corridors"] is not None and (src, dst) not in p["corridors"]:
        reasons.append(f"corridor {src}->{dst} not supported")
    if usd < p["min_usd"]:
        reasons.append("below provider minimum")
    if usd > p["max_usd"]:
        reasons.append("above provider maximum")
    if deadline_days is not None and p["delivery_days"] > int(deadline_days):
        reasons.append(f"delivery takes {p['delivery_days']} day(s), deadline is {deadline_days}")
    if net <= 0:
        reasons.append("fee exceeds amount")

    return {
        "provider_id": p["id"],
        "provider": p["name"],
        "send_amount": q(amount),
        "send_currency": src,
        "fee": q(fee),
        "applied_rate": rate.quantize(RATE_Q),
        "recipient_gets": q(recipient),
        "recipient_currency": dst,
        "total_cost_pct": q(cost_pct),
        "delivery_days": p["delivery_days"],
        "eligible": not reasons,
        "reasons": reasons,
    }


def compare(amount, src: str, dst: str, deadline_days=None) -> dict:
    amount = D(amount)
    if amount <= 0:
        raise ValueError("amount must be positive")
    options = [evaluate(p, amount, src, dst, deadline_days) for p in PROVIDERS]
    options.sort(key=lambda o: (not o["eligible"], -o["recipient_gets"], o["delivery_days"]))
    eligible = [o for o in options if o["eligible"]]
    best = eligible[0] if eligible else None
    saving = q(eligible[0]["recipient_gets"] - eligible[-1]["recipient_gets"]) if len(eligible) > 1 else q(0)
    return {
        "amount": q(amount),
        "from": norm_ccy(src),
        "to": norm_ccy(dst),
        "mid_rate": mid_rate(src, dst).quantize(RATE_Q),
        "deadline_days": deadline_days,
        "options": options,
        "best": best,
        "saving_vs_worst_eligible": saving,
    }


def source_needed(p: dict, target_recipient, src: str, dst: str) -> Decimal:
    """Inverse of evaluate(): source amount so the recipient gets exactly target."""
    rate = mid_rate(src, dst) * (1 - p["fx_margin"])
    return (D(target_recipient) / rate + _fixed_fee_src(p, src)) / (1 - p["pct_fee"])
