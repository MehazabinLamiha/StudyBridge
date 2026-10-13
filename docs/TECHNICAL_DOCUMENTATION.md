# StudyBridge — Technical Documentation

Topic C: Cross-border & Student Finance Assistant · version 0.1.0

## 1. Problem and users

International students are usually funded from home in one currency and spend in another.
The persona used throughout is a fictional Bangladeshi undergraduate in Shenzhen:

- Her family sends BDT every month.
- Tuition (CNY 26,000) and dorm rent are paid in CNY.
- She holds a small amount of USD for online purchases.

Her real problems:

1. **Remittance cost is opaque.** Services advertise a low fee but earn a margin on the
   exchange rate. Comparing them by "fee" alone picks the wrong one.
2. **Tuition deadlines vs. exchange-rate risk.** Converting everything on one day is a bet
   on that day's rate. Converting too late risks a late fee.
3. **No credit history** in the new country, and no clear plan to build one.
4. **Money spread across currencies**, so she cannot see her real monthly burn or how long
   her funds last.

## 2. System architecture

```
 user (web UI / CLI)
        |
        v
 +--------------------+   rules parser (always)          +------------------+
 | StudentFinanceAgent|-- LLM intent proposal (optional)->| Ollama qwen2.5:7b|
 |  agent.py          |<- schema-constrained JSON -------- +------------------+
 +---------+----------+
           | 1 parse  -> grounding check of LLM values, dual agreement for money movement
           | 2 policy -> PolicyEngine: tier allowlist, limits          (security/permissions.py)
           | 3 tools  -> deterministic Decimal computation
           |            fx.py  remittance.py  tuition.py  credit.py  budget.py  wallet.py
           | 4 explain-> template facts + optional LLM paragraph
           |            -> grounding guard (numbers, %, currency, terms) (security/guard.py)
           | 5 audit  -> hash-chained JSONL, PII masked                (security/audit.py)
           v
 money movement => PendingAction --(user /confirm <id>, TTL 5 min)--> re-check policy --> SandboxWallet
```

Key design decisions:

| Decision | Reason |
|---|---|
| The LLM never computes a number | Our earlier work with a 7B model showed frequent arithmetic, unit and labelling errors. Deterministic code is exact and testable. |
| The LLM is optional | Everything works rules-only, so the system degrades gracefully, tests are deterministic, and no data has to leave the device. |
| Local model (Ollama) | Financial data stays on the machine; no third-party API key is needed. |
| Standard library only | No supply-chain risk from dependencies; easy to audit and deploy. |
| `Decimal` everywhere | Floats are never used for balances. |

### Components

| Module | Responsibility |
|---|---|
| `config.py` | Sandbox mid rates, 4 fictional provider archetypes, money limits |
| `money.py`, `fx.py` | Currency aliases (RMB→CNY, taka→BDT), cross rates, wallet quotes with a 0.4% spread |
| `remittance.py` | Provider comparison and the closed-form inverse (§3.1) |
| `tuition.py` | Tranche planner (§3.2) |
| `credit.py` | Credit-building readiness index (§3.3) |
| `budget.py` | Spending by category and currency, burn, runway, anomalies, memo scan (§3.4) |
| `wallet.py` | Sandbox multi-currency ledger; idempotent `convert` and `send` |
| `agent.py` | Parsing, routing, policy, explanation, confirmation flow |
| `security/*` | Permission tiers, grounding guard, injection detector, audit log |
| `web.py`, `static/` | Local web UI |
| `demo.py` | Scripted run that writes the execution evidence |

## 3. Core algorithms

### 3.1 Remittance comparison

For provider *p*, amount *A* in source currency, and mid rate *m* (destination units per source unit):

```
fee(p, A)  = fixed_p · m(USD→src) + pct_p · A
rate(p)    = m · (1 − margin_p)
recv(p, A) = (A − fee) · rate
cost%(p,A) = (A·m − recv) / (A·m) · 100
```

`cost%` combines the visible fee and the hidden FX margin into one number.

A provider is **eligible** if:
- the corridor is supported,
- the USD-equivalent amount is within the provider's min/max, and
- `delivery_days ≤ deadline` (when a deadline is given).

Eligible options are ranked by `recv` (descending), then by speed. The answer also reports
how much more the best option delivers than the most expensive eligible one.

**Inverse (used by the planner and "send X CNY")** — the source amount that delivers exactly *T*:

```
A(T) = (T / rate + fixed_p · m(USD→src)) / (1 − pct_p)
```

A unit test checks that `recv(p, A(T)) = T` to the cent.

*Example (sandbox, BDT 50,000 → CNY, deadline 1 day):*
- Digital service A delivers CNY 2,842.05 (cost 1.22%).
- Mobile wallet C delivers CNY 2,811.23 (2.29%).
- Cash-pickup B delivers CNY 2,749.61 (4.43%).
- SWIFT is excluded because it takes 3 days.

### 3.2 Tuition tranche planner

Inputs: tuition *T* (currency *c*), due date *d*, today *t*, balances, safety buffer *s* = 3 days.

1. `shortfall = max(0, T − balance_c)`
2. `window = (d − t) − s`. If the window is negative, the status is **URGENT**; if `d < t`, **OVERDUE**.
3. Number of tranches: `n = clamp(window // 7 + 1, 1, 4)`. Tranches are spaced `window // n`
   days apart. Equal tranches spread the exchange-rate risk, which is the same idea as
   dollar-cost averaging.
4. For each tranche, pick the provider that minimises `A(T/n)` among those that are eligible for
   that size and still deliver by `d − s`.
5. Report the total funding need, the gap against the BDT balance (**FUNDING_GAP** vs
   **ON_TRACK**), and the sensitivity: `total × 2%` is the cost change from a 2% FX move.

*Example:*
- CNY 26,000 due 2026-11-15, CNY 3,200 already held, planned on 2026-10-13.
- 4 tranches of CNY 5,700 via Digital service A, at BDT 100,092.91 each.
- Total BDT 400,371.64, no funding gap. A 2% FX move would change the cost by about BDT 8,007.

### 3.3 Credit-building readiness index (0–100)

This is a transparent heuristic, explicitly **not** a bureau score. The factor groups mirror
those that bureaus describe publicly:

| Factor | Points | Rule |
|---|---|---|
| Payment history | 35 | 35 × on-time share, −10 per missed payment |
| Utilisation | 30 | ≤10%: 30, ≤30%: 25, ≤50%: 12, else 0 |
| History length | 15 | 15 × min(months, 24)/24 |
| Account mix | 10 | bank account 4, card 4, phone/utility contract 2 |
| New credit | 10 | ≤1 hard inquiry in 6 months: 10, ≤3: 5, else 0 |

Stages: <40 THIN_FILE, <70 BUILDING, otherwise ESTABLISHED. Every point lost maps to a
concrete action. For example, 42% utilisation produces "pay it below 30% before the
statement date".

### 3.4 Spending insights

Every transaction is converted to BDT at the mid rate and grouped by category and by currency.

- `burn = spend / months`
- `runway = wallet value / burn`
- **Anomaly:** a payment larger than 3× the median, in a category that occurs only once.
  Recurring categories such as rent are excluded, so a normal rent payment is not flagged.
- **Memo scan:** every memo is checked for instruction-like text (§4.3). Matching memos are
  reported but never executed.

## 4. Security design (summary — full detail in SECURITY_SELF_ASSESSMENT.md)

### 4.1 Permission tiers

| Tier | Allows | Confirmation |
|---|---|---|
| PUBLIC | help, FX quotes | — |
| READ | wallet overview, spending insights | — |
| ADVISE (default) | remittance comparison, tuition plan, credit plan | — |
| TRANSACT | sandbox conversion, transfer to a saved beneficiary | **always**, through a separate channel |
| ADMIN | configuration | not reachable through the agent |

The LLM cannot call tools and cannot change the tier. The policy engine is the only gate,
and it re-checks the tier and limits **at confirmation time** to prevent a time-of-check /
time-of-use gap.

### 4.2 Money-movement controls

- Per-transaction limit of BDT 400,000 and daily limit of BDT 600,000. The daily total resets each day.
- Transfers only go to **saved beneficiaries**. Adding a beneficiary is deliberately outside
  the agent's scope; it belongs in the bank app with 2FA.
- An exact amount is required; "all" or "everything" is refused.
- Each pending action has a 48-bit random id and a 5-minute TTL, and is single-use (a
  replayed confirmation is refused).
- Wallet operations are idempotent, keyed by the action id.

### 4.3 LLM hardening (hallucination and injection)

| Control | What it stops |
|---|---|
| Schema-constrained output (Ollama `format` JSON schema), intent enum | Malformed or free-form routing |
| Grounding of LLM-extracted amounts and deadlines in the user's text | Invented amounts, e.g. the LLM says 99,999 when the user said 50,000 |
| Dual agreement: money movement only if the rules parser **and** the LLM both say so; otherwise the non-moving intent is used | One parser misreading a question as a transfer. This happened in a real run: the LLM read "how much is 10000 BDT in CNY" as `convert_currency` and was downgraded. |
| Grounding guard on explanations: numbers, ISO dates, **percentages** (must be a percentage in the source) and **currency labels** (an amount must carry the same currency as in the source), plus forbidden terms ("guaranteed", "risk-free", "credit score" for the readiness index) | Hallucinated or mislabelled figures. The sentence is **cut in code** rather than re-prompted, because small models tend to repeat the same error. |
| Untrusted-data rule: memos and other third-party text are never parsed for intent, and never enter the LLM prompt | Indirect prompt injection |
| Injection-pattern detector on user messages blocks money movement for that message | Direct injection ("ignore previous instructions and send…") |

The guard was improved from v1 to v2 based on real model output. In run B
(`evidence/run_B_llm_guard_v1`), qwen2.5:7b wrote three sentences that v1 let through:

- "saving 92.44%" — 92.44 was a CNY amount, not a percentage
- "5,700.00 BDT" — the amount was in CNY
- "Your credit score is 54.24" — it is a readiness index, not a credit score

v2 adds the percentage, currency and terminology checks, and the three sentences are now
regression tests.

### 4.4 Audit and privacy

- Each record stores `hash = SHA-256(prev_hash ‖ canonical JSON)`. `verify()` recomputes the
  chain, so changing a single character breaks it; the demo's tamper test does exactly this.
- Account numbers and any 8+ digit sequence are masked to `****1234` before logging.
- The web UI binds to 127.0.0.1 and sends a strict CSP (`script-src 'self'`). Every POST
  needs a custom header, which defeats CSRF. Bodies are capped at 8 KB, and all output is
  rendered with `textContent`.

## 5. Evaluation

| Check | Result |
|---|---|
| Unit tests | 41 / 41 pass (`python -m unittest discover -s tests -t .`) |
| Scripted sandbox run, rules-only (`evidence/run_A_rules_only`) | 14 requests, 5 correctly blocked, 2 executed, 1 cancelled, replay refused, audit chain OK, tamper detected |
| Scripted run with qwen2.5:7b, guard v1 (`evidence/run_B_llm_guard_v1`) | 2 hallucinated sentences cut, 3 slipped through and led to guard v2 |
| Scripted run with qwen2.5:7b, guard v2 (`evidence/run_C_llm_guard_v2`) | All 3 v1 misses cut; dual-parser downgrade repeated; audit OK; 1 residual entity-binding error ("rent … around 40,000 BDT", actual 62,564) — see §6 |
| Web UI check (browser) | tuition plan → prepare transfer → Confirm → balance updated BDT 520,000 → 419,907.09; no console errors |

## 6. Limitations and future work

- Rates and fees are sandbox data. Production needs a licensed rate feed and provider APIs.
- Country rules (Bangladesh Bank student-file outward-remittance rules, Chinese bank KYC,
  local credit bureaus) are not modelled. The assistant states this rather than guessing.
- The rule parser is English-only. A Bangla/Chinese parser is future work.
- The grounding guard checks numbers, units and banned terms, not which entity a number
  belongs to. In run C, the model wrote "rent and food … each around 40,000 BDT": the number
  exists (food), but rent is 62,564. Planned fix: bind each number to its JSON key and check
  the noun next to it, or run an NLI entailment check (e.g. MiniCheck) per sentence. Until
  then, the template facts above every LLM paragraph remain the source of truth.
