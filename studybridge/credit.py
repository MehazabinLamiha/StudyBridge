"""Credit-building readiness for newcomers with a thin credit file.

This is a transparent heuristic index (0-100), NOT an official credit score.
Credit bureaus differ by country; the weights mirror the factor groups that
most bureaus publicly describe (payment history, utilisation, length of
history, account mix, recent applications).
"""
from decimal import Decimal

from .money import D, q

WEIGHTS = {"payment_history": 35, "utilisation": 30, "history_length": 15, "account_mix": 10, "new_credit": 10}


def assess(profile: dict) -> dict:
    on_time = int(profile.get("on_time_payments_12m", 0))
    missed = int(profile.get("missed_payments_12m", 0))
    months = int(profile.get("months_in_country", 0))
    limit = D(profile.get("card_limit", 0))
    balance = D(profile.get("card_balance", 0))
    inquiries = int(profile.get("hard_inquiries_6m", 0))

    total = on_time + missed
    payment = Decimal(35) * on_time / total if total else Decimal(0)
    payment = max(Decimal(0), payment - 10 * missed)

    utilisation_pct = (balance / limit * 100) if limit > 0 else None
    if utilisation_pct is None:
        util_pts = 0
    elif utilisation_pct <= 10:
        util_pts = 30
    elif utilisation_pct <= 30:
        util_pts = 25
    elif utilisation_pct <= 50:
        util_pts = 12
    else:
        util_pts = 0

    history = Decimal(15) * min(months, 24) / 24
    mix = (4 if profile.get("has_local_bank_account") else 0) \
        + (4 if profile.get("has_credit_card") else 0) \
        + (2 if profile.get("has_phone_contract") else 0)
    new_credit = 10 if inquiries <= 1 else 5 if inquiries <= 3 else 0

    parts = {
        "payment_history": q(payment), "utilisation": q(util_pts),
        "history_length": q(history), "account_mix": q(mix), "new_credit": q(new_credit),
    }
    score = q(sum(parts.values()))
    stage = "THIN_FILE" if score < 40 else "BUILDING" if score < 70 else "ESTABLISHED"

    actions = []
    if not profile.get("has_local_bank_account"):
        actions.append("Open a local bank account in your own name; most credit products require one.")
    if not profile.get("has_credit_card"):
        actions.append("Ask your bank for a secured or student credit card with a small limit.")
    if utilisation_pct is not None and utilisation_pct > 30:
        actions.append(f"Card utilisation is {q(utilisation_pct)}%; pay it below 30% of the limit before the statement date.")
    if missed:
        actions.append("Set up automatic minimum payments so no due date is missed again.")
    if not profile.get("has_phone_contract"):
        actions.append("A post-paid phone or utility contract in your name adds positive payment history.")
    if inquiries > 1:
        actions.append("Avoid new credit applications for 6 months; each one is a hard inquiry.")
    if not actions:
        actions.append("Keep paying in full every month and keep utilisation under 10%.")

    return {
        "readiness_index": score, "stage": stage, "components": parts, "weights": WEIGHTS,
        "utilisation_pct": q(utilisation_pct) if utilisation_pct is not None else None,
        "actions": actions,
        "disclaimer": "Heuristic readiness index, not an official credit score. Rules differ by country.",
    }
