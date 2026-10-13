"""Output and input guards.

numeric grounding guard
    Every number (and ISO date) the LLM writes must match a number in the
    tool results or the user's own message, within a rounding tolerance.
    A sentence with an ungrounded number is cut in code; the model is not
    asked to fix itself, because small models often repeat the same error.

untrusted-text handling
    Transaction memos, beneficiary names and similar fields come from third
    parties. They are scanned for instruction-like text and are never used
    to choose a tool or fill an argument.
"""
import re
from decimal import Decimal, InvalidOperation

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUM = re.compile(r"(?<![A-Za-z])-?\d[\d,]*(?:\.\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
SMALL_INT_OK = 10          # bare integers up to this are counts/list markers
REL_TOL = Decimal("0.005")
ABS_TOL = Decimal("0.01")

_INJECTION = re.compile(
    r"ignore (all|any|previous|prior|the above)|disregard .*instruction|system prompt|"
    r"you are now|developer mode|\bjailbreak\b|transfer (all|everything)|send (all|everything)|"
    r"new instruction|act as|override",
    re.IGNORECASE,
)


def looks_like_injection(text: str) -> bool:
    return bool(text) and bool(_INJECTION.search(text))


def numbers_in(text: str) -> list:
    text = _DATE.sub(" ", text)
    out = []
    for tok in _NUM.findall(text):
        tok = tok.replace(",", "").rstrip(".")
        try:
            out.append(Decimal(tok))
        except InvalidOperation:
            continue
    return out


def dates_in(text: str) -> set:
    return set(_DATE.findall(text))


def _grounded(x: Decimal, pool: list) -> bool:
    ax = abs(x)
    if ax == ax.to_integral_value() and ax <= SMALL_INT_OK:
        return True
    for s in pool:
        s = abs(s)
        if abs(ax - s) <= max(ABS_TOL, REL_TOL * s):
            return True
    return False


_NUMTXT = r"(-?\d[\d,]*(?:\.\d+)?)"
_CODES = r"(BDT|CNY|USD|THB|EUR|RMB|YUAN|TAKA)"
_PAIR_BEFORE = re.compile(r"\b" + _CODES + r"\s*" + _NUMTXT, re.IGNORECASE)
_PAIR_AFTER = re.compile(_NUMTXT + r"\s*" + _CODES + r"\b", re.IGNORECASE)
_PCT = re.compile(_NUMTXT + r"\s*%")
_PCT_KEY = re.compile(r'"[^"]*pct[^"]*"\s*:\s*"?' + _NUMTXT)
_CODE_NORM = {"RMB": "CNY", "YUAN": "CNY", "TAKA": "BDT"}

# Claims a finance assistant must never make, whatever the numbers say.
ALWAYS_FORBIDDEN = [r"\bguarantee", r"\brisk[- ]free\b", r"\bno risk\b"]


def _dec(tok: str) -> Decimal:
    return Decimal(tok.replace(",", "").rstrip("."))


def _pairs(text: str) -> list:
    text = _DATE.sub(" ", text)
    out = [(_CODE_NORM.get(c.upper(), c.upper()), _dec(n)) for c, n in _PAIR_BEFORE.findall(text)]
    out += [(_CODE_NORM.get(c.upper(), c.upper()), _dec(n)) for n, c in _PAIR_AFTER.findall(text)]
    return out


def _close(a: Decimal, b: Decimal) -> bool:
    a, b = abs(a), abs(b)
    return abs(a - b) <= max(ABS_TOL, REL_TOL * b)


def enforce_grounding(text: str, sources: list, forbidden: list = ()) -> tuple:
    """Return (clean_text, removed_sentences).

    A sentence is cut when it contains
      - a number or ISO date that is not in the sources,
      - a percentage whose value is not a percentage in the sources,
      - an amount labelled with a different currency than in the sources,
      - a forbidden claim (e.g. 'guaranteed', or a term the tool must not use).
    """
    pool, pool_dates, pool_pairs, pool_pct = [], set(), [], []
    for s in sources:
        pool.extend(numbers_in(s))
        pool_dates |= dates_in(s)
        pool_pairs += _pairs(s)
        pool_pct += [_dec(n) for n in _PCT.findall(s)] + [_dec(n) for n in _PCT_KEY.findall(s)]
    banned = [re.compile(p, re.IGNORECASE) for p in list(ALWAYS_FORBIDDEN) + list(forbidden)]

    kept, removed = [], []
    for sent in _SENTENCE.split(text):
        if not sent.strip():
            continue
        bad = [n for n in numbers_in(sent) if not _grounded(n, pool)]
        bad += [d for d in dates_in(sent) if d not in pool_dates]
        bad += [n for n in map(_dec, _PCT.findall(sent)) if not any(_close(n, p) for p in pool_pct)]
        for ccy, n in _pairs(sent):
            known = {pc for pc, pn in pool_pairs if _close(n, pn)}
            if known and ccy not in known:
                bad.append(f"{n} {ccy}")
        bad += [b.pattern for b in banned if b.search(sent)]
        (removed if bad else kept).append(sent.strip())
    return " ".join(kept), removed


def amount_grounded_in(amount, message: str) -> bool:
    """True if `amount` literally appears in the user's message."""
    if amount is None:
        return True
    try:
        a = Decimal(str(amount))
    except InvalidOperation:
        return False
    return any(abs(a - n) <= ABS_TOL for n in numbers_in(message))


def wrap_untrusted(text: str, limit: int = 200) -> str:
    clean = "".join(ch for ch in str(text) if ch.isprintable())[:limit]
    return f"<untrusted_data>{clean}</untrusted_data>"
