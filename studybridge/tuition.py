"""Tuition payment planner.

Algorithm
1. shortfall = tuition - balance already held in the tuition currency.
2. last safe send date = due date - safety buffer - provider delivery days.
3. The shortfall is split into equal tranches, one per week of the window
   (capped at max_tranches). Buying foreign currency in several tranches
   averages the exchange rate instead of betting everything on one day.
4. For every tranche, each provider's required source amount is computed
   with the closed-form inverse in remittance.source_needed(); the cheapest
   provider that is eligible for that size and fast enough is chosen.
5. The plan reports the total funding need, any gap against the funding
   balance, and how much a 2% exchange-rate move would change the cost.
"""
from datetime import date, timedelta
from decimal import Decimal

from .config import PROVIDERS
from .money import D, norm_ccy, q, to_usd
from .remittance import source_needed

FX_SHOCK = Decimal("0.02")


def _cheapest_provider(target, src, dst, max_delivery_days):
    best = None
    for p in PROVIDERS:
        if p["corridors"] is not None and (src, dst) not in p["corridors"]:
            continue
        if p["delivery_days"] > max_delivery_days:
            continue
        need = source_needed(p, target, src, dst)
        usd = to_usd(need, src)
        if not (p["min_usd"] <= usd <= p["max_usd"]):
            continue
        if best is None or need < best[1]:
            best = (p, need)
    return best


def plan(tuition_amount, tuition_ccy: str, due_date: date, today: date, balances: dict,
         funding_ccy: str = "BDT", safety_days: int = 3, max_tranches: int = 4) -> dict:
    tuition_ccy, funding_ccy = norm_ccy(tuition_ccy), norm_ccy(funding_ccy)
    tuition = D(tuition_amount)
    held = D(balances.get(tuition_ccy, 0))
    funding_balance = D(balances.get(funding_ccy, 0))
    shortfall = max(Decimal(0), tuition - held)
    days_left = (due_date - today).days

    base = {
        "tuition": q(tuition), "tuition_currency": tuition_ccy,
        "due_date": due_date.isoformat(), "days_left": days_left,
        "already_held": q(held), "shortfall": q(shortfall),
        "funding_currency": funding_ccy, "funding_balance": q(funding_balance),
        "tranches": [],
    }
    if shortfall == 0:
        return {**base, "status": "COVERED", "total_funding_needed": q(0), "funding_gap": q(0)}
    if days_left < 0:
        return {**base, "status": "OVERDUE", "total_funding_needed": q(0), "funding_gap": q(0),
                "advice": "The due date has passed. Contact the university finance office before sending money."}

    # Window that still leaves the safety buffer after the slowest acceptable delivery.
    window = days_left - safety_days
    if window < 0:
        status_hint = "URGENT"
        window = 0
    else:
        status_hint = None

    n = max(1, min(max_tranches, window // 7 + 1))
    tranche_target = shortfall / n
    step = window // n if n > 1 else 0

    tranches, total = [], Decimal(0)
    for i in range(n):
        send_on = today + timedelta(days=i * step)
        latest_delivery = (due_date - timedelta(days=safety_days) - send_on).days
        choice = _cheapest_provider(tranche_target, funding_ccy, tuition_ccy, max(latest_delivery, 0))
        if choice is None:
            choice = _cheapest_provider(tranche_target, funding_ccy, tuition_ccy, days_left)
            status_hint = "URGENT"
        if choice is None:
            return {**base, "status": "NO_PROVIDER", "total_funding_needed": q(0), "funding_gap": q(0),
                    "advice": "No sandbox provider can deliver this amount in time."}
        p, need = choice
        total += need
        tranches.append({
            "n": i + 1, "send_on": send_on.isoformat(), "provider": p["name"], "provider_id": p["id"],
            "recipient_gets": q(tranche_target), "send_amount": q(need),
            "delivery_days": p["delivery_days"],
        })

    gap = max(Decimal(0), total - funding_balance)
    status = status_hint or ("FUNDING_GAP" if gap > 0 else "ON_TRACK")
    return {
        **base, "status": status, "tranches": tranches,
        "total_funding_needed": q(total), "funding_gap": q(gap),
        "fx_sensitivity_2pct": q(total * FX_SHOCK),
        "safety_days": safety_days,
    }
