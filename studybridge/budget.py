"""Multi-currency spending insights.

Every transaction is converted to the home currency at the sandbox mid rate,
grouped by category and by currency, and turned into a monthly burn rate and
a runway (how many months the current wallet lasts at that burn).
Transaction memos are untrusted text: they are never interpreted, only
scanned so suspicious ones can be reported.
"""
from collections import defaultdict
from decimal import Decimal
from statistics import median

from .money import D, convert_mid, q
from .security.guard import looks_like_injection


def analyze(transactions: list, wallet_value_home, home: str = "BDT") -> dict:
    by_cat, by_ccy, months = defaultdict(Decimal), defaultdict(Decimal), set()
    income_home, sizes, suspicious = Decimal(0), [], []

    for t in transactions:
        amt = D(t["amount"])
        home_amt = convert_mid(amt, t["currency"], home)
        if looks_like_injection(t.get("memo", "")):
            suspicious.append(t["id"])
        if amt >= 0:
            income_home += home_amt
            continue
        spend = -home_amt
        by_cat[t["category"]] += spend
        by_ccy[t["currency"]] += -amt
        months.add(t["date"][:7])
        sizes.append(spend)

    total = sum(by_cat.values(), Decimal(0))
    n_months = max(1, len(months))
    burn = total / n_months
    med = Decimal(median(sizes)) if sizes else Decimal(0)
    # Categories paid two or more times (rent, food...) are routine, not anomalies.
    cat_counts = defaultdict(int)
    for t in transactions:
        if D(t["amount"]) < 0:
            cat_counts[t["category"]] += 1
    large = [
        {"id": t["id"], "date": t["date"], "category": t["category"],
         "amount_home": q(-convert_mid(D(t["amount"]), t["currency"], home))}
        for t in transactions
        if D(t["amount"]) < 0 and -convert_mid(D(t["amount"]), t["currency"], home) > 3 * med
        and cat_counts[t["category"]] < 2
    ]
    ranked = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "home_currency": home,
        "months_covered": n_months,
        "total_spend_home": q(total),
        "monthly_burn_home": q(burn),
        "income_home": q(income_home),
        "runway_months": q(D(wallet_value_home) / burn) if burn > 0 else None,
        "by_category": [
            {"category": c, "amount_home": q(v), "share_pct": q(v / total * 100) if total else q(0)}
            for c, v in ranked
        ],
        "spend_by_currency": {c: q(v) for c, v in by_ccy.items()},
        "unusually_large": large,
        "suspicious_memo_ids": suspicious,
    }
