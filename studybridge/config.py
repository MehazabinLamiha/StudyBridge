"""Static configuration for the StudyBridge sandbox.

Every rate, fee and limit in this file is ILLUSTRATIVE SANDBOX DATA. It is not
a live quote from any real provider. A production deployment replaces
MID_PER_USD with a licensed rate feed and PROVIDERS with provider APIs.
"""
from decimal import Decimal as D

HOME_CURRENCY = "BDT"
SUPPORTED_CURRENCIES = ("BDT", "CNY", "USD", "THB", "EUR")

CURRENCY_ALIASES = {
    "BDT": "BDT", "TAKA": "BDT", "TK": "BDT", "৳": "BDT",
    "CNY": "CNY", "RMB": "CNY", "YUAN": "CNY", "¥": "CNY",
    "USD": "USD", "DOLLAR": "USD", "DOLLARS": "USD", "$": "USD",
    "THB": "THB", "BAHT": "THB",
    "EUR": "EUR", "EURO": "EUR", "EUROS": "EUR", "€": "EUR",
}

# Units of each currency per 1 USD (sandbox mid-market snapshot).
MID_PER_USD = {
    "USD": D("1"),
    "BDT": D("123.39"),
    "CNY": D("7.10"),
    "THB": D("33.20"),
    "EUR": D("0.86"),
}
RATE_SOURCE = "SANDBOX snapshot (illustrative, not a live quote)"

# Spread charged on conversions inside the StudyBridge wallet.
WALLET_FX_SPREAD = D("0.004")

# Fictional provider archetypes. Names are deliberately generic so no real
# company's pricing is misrepresented.
PROVIDERS = [
    {
        "id": "bank_swift", "name": "Bank wire (SWIFT)",
        "fixed_fee_usd": D("25"), "pct_fee": D("0"), "fx_margin": D("0.025"),
        "delivery_days": 3, "min_usd": D("50"), "max_usd": D("50000"),
        "corridors": None,
    },
    {
        "id": "digital_a", "name": "Digital transfer service A",
        "fixed_fee_usd": D("1.50"), "pct_fee": D("0.0045"), "fx_margin": D("0.004"),
        "delivery_days": 1, "min_usd": D("10"), "max_usd": D("10000"),
        "corridors": None,
    },
    {
        "id": "cash_b", "name": "Cash-pickup network B",
        "fixed_fee_usd": D("8"), "pct_fee": D("0.01"), "fx_margin": D("0.015"),
        "delivery_days": 0, "min_usd": D("5"), "max_usd": D("3000"),
        "corridors": None,
    },
    {
        "id": "wallet_c", "name": "Mobile wallet C",
        "fixed_fee_usd": D("0"), "pct_fee": D("0.015"), "fx_margin": D("0.008"),
        "delivery_days": 0, "min_usd": D("1"), "max_usd": D("1000"),
        "corridors": {("BDT", "CNY"), ("BDT", "THB"), ("BDT", "USD")},
    },
]

# Money-movement guardrails, expressed in HOME_CURRENCY.
LIMITS = {
    "per_tx_home": D("400000"),
    "daily_home": D("600000"),
}
CONFIRM_TTL_SECONDS = 300

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b"
