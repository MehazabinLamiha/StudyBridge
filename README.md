# StudyBridge — Cross-border & Student Finance Assistant

**Topic C** submission. StudyBridge is an AI assistant for international students who are
funded from home and pay in a foreign currency. The demo persona is a fictional Bangladeshi
student in Shenzhen: her family sends BDT, her tuition and rent are in CNY, and she holds
some USD.

It helps with the four pain points named in Topic C:

| Pain point | What StudyBridge does |
|---|---|
| Remittances | Ranks providers by **what the recipient actually gets**, including the hidden FX mark-up, and filters by deadline, corridor and limits |
| Tuition payments | Builds a dated plan that splits the shortfall into tranches (averaging FX risk), picks the cheapest provider per tranche, and flags funding gaps and late-payment risk |
| Credit building | Gives a transparent 0–100 readiness index for a thin credit file, plus prioritised actions |
| Multi-currency management | Shows a multi-currency wallet, spending by category and currency, monthly burn and runway; does sandbox conversions and transfers |

> **Sandbox only.** All rates, fees and accounts are illustrative sample data
> (`studybridge/config.py`, `data/sample_profile.json`). No real money or account is touched.

## Design principle: the LLM never owns a number or a permission

- Every number comes from deterministic Python (`Decimal` arithmetic).
- The LLM (local **Ollama `qwen2.5:7b`**, optional) only (1) proposes a schema-constrained
  intent and (2) writes a short plain-language explanation.
- Each LLM value is checked against the user's message. Each explanation passes a numeric,
  unit and terminology **grounding guard**, which cuts unsupported sentences in code.
- Money movement needs **permission tier TRANSACT**, must stay within **per-transaction and
  daily limits**, can only go to a **saved beneficiary**, and needs **explicit user
  confirmation** through a separate channel. Every step is written to a **hash-chained
  audit log**.

See [docs/TECHNICAL_DOCUMENTATION.md](docs/TECHNICAL_DOCUMENTATION.md) and
[docs/SECURITY_SELF_ASSESSMENT.md](docs/SECURITY_SELF_ASSESSMENT.md).

## Quick start

Requires Python 3.10+. There are **no third-party dependencies**; only the standard library is used.

```bash
git clone https://github.com/MehazabinLamiha/StudyBridge.git && cd StudyBridge
python -m unittest discover -s tests -t .        # 41 tests
python -m studybridge --today 2026-10-13 demo     # scripted sandbox run -> evidence/
python -m studybridge --tier TRANSACT web         # http://127.0.0.1:8765
python -m studybridge chat                        # terminal chat
```

On Windows, use `py` instead of `python` if `python` opens the Microsoft Store.

### Optional: local LLM

```bash
ollama pull qwen2.5:7b
python -m studybridge --llm --tier TRANSACT web
```

If Ollama is not reachable, StudyBridge logs a warning and runs rules-only. Every feature
still works.

### Options

| Flag | Meaning |
|---|---|
| `--tier PUBLIC\|READ\|ADVISE\|TRANSACT` | Permission tier granted to the session (default `ADVISE`, which cannot move money) |
| `--llm` / `--model` | Use Ollama for intent parsing and explanations |
| `--today YYYY-MM-DD` | Fix the planner date for reproducible runs |
| `--profile path.json` | Use another sandbox profile |
| `--audit path.jsonl` | Audit log location (default `var/audit.jsonl`) |

`python -m studybridge verify-audit` checks the hash chain and exits with code 1 if it was tampered with.

## Deployment

**Local (recommended for the sandbox):** the commands above. The web server binds to
`127.0.0.1` only.

**Docker:**

```bash
docker build -t studybridge .
docker run --rm -p 127.0.0.1:8765:8765 studybridge
# with Ollama running on the host:
docker run --rm -p 127.0.0.1:8765:8765 -e OLLAMA_URL=http://host.docker.internal:11434 studybridge --llm web --host 0.0.0.0
```

Do not expose the web UI to the internet. It has no user authentication, because it is a
single-user sandbox (see the known-risk list).

## Example requests

```
show my wallet balance
how much is 10000 BDT in CNY
compare the cheapest way to send 50000 BDT to CNY within 1 day
plan my tuition payment
show my spending and runway
how can I build credit
send 5700 CNY to my university for tuition        (TRANSACT tier, then /confirm <id>)
convert 20000 BDT to CNY
```

## Repository layout

```
studybridge/
  agent.py          orchestrator: parse -> policy -> tools -> explain -> audit
  config.py         sandbox rates, provider archetypes, limits
  money.py fx.py    Decimal money and FX quotes
  remittance.py     provider comparison + closed-form inverse
  tuition.py        tranche planner
  credit.py         credit-building readiness index
  budget.py         spending insights, runway, anomaly and memo scan
  wallet.py         sandbox multi-currency wallet (idempotent operations)
  llm.py            Ollama client (stdlib urllib)
  security/
    permissions.py  tiers, allowlist, limits
    guard.py        numeric/unit/terminology grounding guard, injection detector
    audit.py        hash-chained audit log, PII masking
  web.py static/    local web UI (strict CSP, CSRF header, textContent rendering)
  demo.py           scripted run that writes the execution evidence
tests/              41 unit tests (core algorithms + security controls)
docs/               technical documentation, security self-assessment
evidence/           sandbox operation logs from real runs
data/               fictional sample profile
```

## Test cases

`tests/test_core.py` covers FX, remittance ranking, the deadline, corridor and limit filters,
the exactness of the inverse fee formula, every tuition status (ON_TRACK, FUNDING_GAP, URGENT,
OVERDUE, COVERED), and the credit stages.

`tests/test_security.py` covers:
- tier blocking
- the tool allowlist
- per-transaction, daily and day-rollover limits
- the prepare → confirm → replay-refused flow
- cancel and expiry
- re-checking the tier at confirmation time
- refusing unsaved beneficiaries
- idempotency
- direct and memo prompt injection
- dropping hallucinated amounts
- requiring LLM + rules agreement for money movement
- offline fallback
- the grounding guard, including three regression sentences written by qwen2.5:7b in a real run
- audit tamper detection
- PII masking

## Team

East West University, Bangladesh

- Rafikul Islam Provat
- Mehazabin Hossain Lamiha
- Ariana Ziauddin
- Nura Alam

## Licence

MIT. Sample data is fictional.
