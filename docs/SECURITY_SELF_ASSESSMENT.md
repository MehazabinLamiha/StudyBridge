# StudyBridge — Security Self-Assessment Report

Version 0.1.0 · scope: the sandbox build in this repository

## 1. Assets and threat model

| Asset | Why it matters |
|---|---|
| Wallet balances and transfer capability | Direct financial loss if misused |
| Beneficiary account numbers, transaction history | Personal and financial data |
| Audit log | Evidence of what the agent did, and why |
| Advice correctness | A wrong number in advice can cause real loss, such as a late tuition payment or an expensive provider |

Threat actors and vectors considered:

1. **Prompt injection, direct** — the user's own text tries to override the rules.
2. **Prompt injection, indirect** — third-party text the agent reads (transaction memos,
   beneficiary names, in future news or emails) contains instructions.
3. **LLM error** — hallucinated amounts, units, dates or labels; misread intent.
4. **Over-privileged agent** — the model triggers money movement the user did not intend.
5. **Local web attacks** — CSRF from another site in the same browser, XSS through model output.
6. **Log tampering** — someone edits the audit trail to hide an action.
7. **Replay / double execution** — the same confirmation is used twice.

## 2. Permission-tier implementation

Source: `studybridge/security/permissions.py`, enforced in `agent.py`.

| Tier | Tools | Money moves? | Confirmation |
|---|---|---|---|
| 0 PUBLIC | `help`, `fx_quote` | no | — |
| 1 READ | `wallet_overview`, `spending_insights` | no | — |
| 2 ADVISE (default) | `compare_remittance`, `tuition_plan`, `credit_plan` | no | — |
| 3 TRANSACT | `convert_currency`, `send_money` | sandbox only | **required, every time** |
| 4 ADMIN | configuration | — | **not reachable through the agent** |

How it is enforced:

1. **Allowlist.** Any tool name not in `TOOL_TIERS` is denied (test: `test_unknown_tool_denied`).
2. **Tier check before every tool.** The session tier is set by the user (CLI flag / server
   start), never by the LLM (test: `test_tier_blocks_money_movement`).
3. **Money-moving tools never execute directly.** They create a `PendingAction`:
   - 48-bit random id from `secrets.token_hex`
   - 5-minute TTL
   - single-use
4. **Confirmation arrives on a separate channel** — the `/confirm <id>` command or the web
   button, which calls `/api/confirm`. Text written by the model cannot confirm anything.
5. **Re-check at execution.** Tier and limits are evaluated again when the user confirms,
   which closes the time-of-check / time-of-use gap (test: `test_tier_rechecked_at_confirmation`).
6. **Limits.** Per transaction BDT 400,000; per day BDT 600,000, reset at the date change
   (test: `test_limits`).
7. **Saved beneficiaries only.** The agent cannot add a beneficiary or send to a raw account
   number (test: `test_unsaved_beneficiary_refused`).
8. **Exact amounts only.** "all" / "everything" is refused (test: `test_send_everything_refused`).
9. **Idempotency.** Wallet operations are keyed by the action id, and a replayed
   confirmation is refused (tests: `test_idempotency`, `test_prepare_then_confirm_then_replay`).

## 3. LLM-specific controls

| Risk | Control | Evidence |
|---|---|---|
| Invented amount in the parsed intent | `amount_grounded_in()`: an LLM amount must appear in the user's message, otherwise it is dropped | `test_hallucinated_amount_dropped` |
| Misread intent causes a transfer | Dual agreement: a money-moving intent needs the rules parser **and** the LLM to agree | `test_llm_cannot_create_money_movement_alone`; real case in `evidence/run_B_llm_guard_v1` (request 2) |
| Hallucinated numbers, units, dates in explanations | `enforce_grounding()` cuts the sentence in code | `test_guard_cuts_invented_number` plus 3 regression tests built from real qwen2.5:7b output |
| Misleading claims | Forbidden terms: "guarantee", "risk-free", "no risk"; per tool, "credit score" | `test_forbidden_terms_cut` |
| Direct injection | `looks_like_injection()` blocks money movement for that message | `test_direct_injection_blocks_money_movement` |
| Indirect injection (memo t16 in the sample data) | Memos are never parsed for intent and never sent to the LLM; they are only scanned and reported | `test_memo_injection_reported_not_followed` |
| LLM offline or failing | Falls back to rules-only and logs the failure | `test_llm_offline_falls_back` |
| Data leaving the device | Local Ollama only; no cloud LLM calls | `llm.py` |

## 4. Application and infrastructure controls

| Area | Control |
|---|---|
| Network exposure | The web server binds to `127.0.0.1`; Docker publishes on `127.0.0.1` only |
| CSRF | Every POST requires `Content-Type: application/json` **and** `X-StudyBridge: 1`; browsers cannot add a custom header in a cross-site form |
| XSS | All text rendered with `textContent`; CSP `default-src 'self'; script-src 'self'`; `frame-ancestors 'none'`; `nosniff` |
| Input size | Request body ≤ 8 KB, chat message ≤ 1,000 characters |
| Money precision | `Decimal` everywhere, rounded half-up to cents |
| Audit integrity | SHA-256 hash chain; `verify-audit` exits non-zero on tamper; the demo shows detection on a modified copy |
| Privacy in logs | Account numbers and any 8+ digit sequence are masked to `****1234` |
| Supply chain | Zero third-party Python dependencies; the container runs as a non-root user |
| Secrets | None are required (local model, sandbox data) |

## 5. Known-risk list

| # | Risk | Severity | Status / mitigation | Residual action |
|---|---|---|---|---|
| R1 | **No user authentication on the web UI** | High if exposed | Bound to localhost; single-user sandbox | Add OAuth/OIDC + session cookies (HttpOnly, SameSite=Strict) before any multi-user deployment |
| R2 | Injection detection is pattern-based, so a reworded attack can bypass the detector | Medium | The detector is only one layer: money still needs TRANSACT tier, a saved beneficiary, limits, dual-parser agreement and human confirmation | Add a classifier-based detector; red-team regularly |
| R3 | The grounding guard checks numbers, units and banned terms, not full meaning or which entity a number belongs to. Observed in `evidence/run_C_llm_guard_v2`: "rent … around 40,000 BDT" (actual 62,564) passed | Medium | The facts section is always produced by templates from computed data; the LLM paragraph is optional and labelled "In plain words" | Add an NLI check (e.g. MiniCheck) that each sentence is entailed by the tool JSON |
| R4 | Sandbox rates and fees are static | Medium (advice quality) | Every quote is labelled "SANDBOX snapshot (illustrative)" | Integrate a licensed rate feed with timestamps and a staleness check |
| R5 | Regulatory rules (Bangladesh Bank student-file limits, KYC/AML in China) are not modelled | Medium | Not claimed; transfers are sandbox-only | Add a compliance rule module per corridor; human compliance review |
| R6 | Audit log is tamper-**evident**, not tamper-**proof**: someone with write access can rewrite the whole chain | Low–Medium | Detection of partial edits | Periodically anchor the head hash externally (WORM storage or a signed timestamp) |
| R7 | Pending actions are held in memory and lost on restart | Low | Fails safe: nothing executes | Persist with an expiry if needed |
| R8 | Profile JSON (balances, transactions) is stored unencrypted on disk | Low (fictional data) | Sample data only | Encrypt at rest with an OS keystore for real data |
| R9 | A 7B local model can be slow (≈20–30 s per request with explanations) | Low (usability) | Rules-only mode is instant | Smaller or faster model for parsing; cache explanations |
| R10 | Credit index could be mistaken for an official score | Low | Disclaimer in every answer; "credit score" wording is cut from the LLM text | User research on wording |
| R11 | The rate limit for confirmation attempts is not implemented | Low | 48-bit ids with a 5-minute TTL are not practical to brute-force over localhost | Add per-session attempt limiting |

## 6. Test summary

`python -m unittest discover -s tests -t .` runs 41 tests, all passing. 26 of them are
security tests in `tests/test_security.py`.

## 7. Conclusion

The sandbox meets its security goals for a single-user, local deployment. The LLM cannot
move money, change permissions or put an unverified number in front of the user without the
guard cutting it. R1, R4 and R5 must be resolved before any real-money or multi-user use.
