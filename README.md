---
title: Scrutiny
emoji: 🌖
colorFrom: purple
colorTo: red
sdk: docker
pinned: false
license: apache-2.0
short_description: Get FDCPA violations flagged with statutory citations
---

# Scrutiny

> What your QA misses in 60 minutes, Scrutiny finds in 60 seconds.

Scrutiny audits debt-collection call transcripts against 12 FDCPA/Reg F rules in under 60 seconds. Paste a redacted transcript, get a structured compliance report with verbatim evidence quotes, statutory citations, and an autofail violation summary. Built for the compliance officer who knows that one missed disclosure is a lawsuit — not a coaching opportunity.

## What it does

Scrutiny evaluates debt-collection call transcripts against a 12-rule rubric derived from the **Fair Debt Collection Practices Act (FDCPA, 15 U.S.C. § 1692)** and **Regulation F (12 CFR Part 1006)**. It uses a **dual-path evaluator**:

- **LLM evaluation** for semantic rules (Mini-Miranda, harassment, false threats, etc.) — one call evaluates all transcript-evaluable rules simultaneously
- **Deterministic checks** for data rules (call time compliance) — Python logic parses timestamps and timezones
- **Cross-validation** for hybrid rules — metadata supplements LLM reasoning

## Quickstart

```bash
# Install dependencies
pip install -e ".[dev]"

# Set your LLM provider (anthropic, openai, or openrouter)
cp .env.example .env
# Edit .env with your API key

# Run the smoke test (no API key required)
python test_e2e.py

# Start the web app
uvicorn web_app:app --reload
# Open http://localhost:8000
```

## The 12-Rule Rubric

| ID | Rule | Category | Autofail | Evaluability |
|---|---|---|---|---|
| FDCPA-001 | Mini-Miranda Recital | Disclosure | Yes | Transcript |
| FDCPA-002 | Validation Notice Reference | Disclosure | No | Transcript + Metadata |
| FDCPA-003 | Call Time Compliance | Time | Yes | **Metadata** |
| FDCPA-004 | Third-Party Disclosure | Third-Party | Yes | Transcript |
| FDCPA-005 | Harassment or Abuse | Harassment | Yes | Transcript + Metadata |
| FDCPA-006 | False Representation of Identity | Representation | Yes | Transcript |
| FDCPA-007 | False Threats of Legal Action | Representation | Yes | Transcript |
| FDCPA-008 | Unfair Practices | Unfair | No | Transcript + Metadata |
| FDCPA-009 | Cease-and-Desist Acknowledgment | Consumer Rights | Yes | Transcript + Metadata |
| FDCPA-010 | Dispute Handling | Consumer Rights | Yes | Transcript + Metadata |
| FDCPA-011 | Voicemail Safe Harbor | Voicemail | No | Transcript |
| FDCPA-012 | Attorney Representation | Consumer Rights | Yes | Transcript + Metadata |

Rules are defined in `fdcpa_rubric.json` with evaluation criteria, legal citations, and pass/fail examples.

## Transcript Pipeline

Each demo scenario ships as **3 files**:

| File | Purpose |
|---|---|
| `tx_001_clean_raw.md` | Raw transcript with PII, ASR artifacts, natural dialog |
| `tx_001_clean.json` | Redacted transcript with placeholders (`[CONSUMER_NAME]`, `[PHONE_NUMBER]`, etc.) |
| `tx_001_clean_meta.json` | Metadata sidecar (timestamp, timezone, call attempts, flags, debt amounts) |

### Privacy redaction format

- Person names → `[CONSUMER_NAME]`, `[AGENT_NAME]`
- Phone numbers → `[PHONE_NUMBER]`
- Account numbers → `[ACCOUNT_NUMBER]`
- Organization names → `[AGENCY_NAME]`, `[CREDITOR_NAME]`, `[EMPLOYER]`
- Addresses → `[STREET_ADDRESS]`

### Metadata sidecar fields

```json
{
  "call_timestamp_local": "2026-04-15T14:30:00",
  "consumer_timezone": "America/New_York",
  "call_attempts_7day": 1,
  "validation_notice_sent": true,
  "validation_notice_date": "2026-04-10",
  "attorney_on_record": false,
  "cease_desist_on_file": false,
  "dispute_on_file": false,
  "debt_amount_original": 1247.50,
  "debt_amount_claimed": 1247.50,
  "call_direction": "outbound"
}
```

## Synthetic Transcripts

Five demo scenarios are included in `transcripts/`:

| Transcript | Planted Violation(s) | Agent Persona | Consumer Persona |
|---|---|---|---|
| `tx_001_clean` | None — fully compliant | Professional | Cooperative |
| `tx_002_no_miranda` | Missing Mini-Miranda (FDCPA-001) | Persuasive | Confused |
| `tx_003_voicemail` | 3rd-party disclosure + voicemail safe harbor (FDCPA-004, FDCPA-011) | Persuasive | N/A (voicemail) |
| `tx_004_cease_desist` | Cease-and-desist ignored (FDCPA-009) | Erosion | Confrontational |
| `tx_005_harassment` | Harassment + false threats (FDCPA-005, FDCPA-007) | Abusive | Distressed |

## Architecture

```
redacted transcript ──┐
                      ├──→ [ FastAPI /audit ] ──→ [ evaluator.py ] ──→ compliance report
metadata sidecar  ────┘                              │
                                             ┌────────┴────────┐
                                             │  1 LLM call      │
                                             │  All text rules  │
                                             │  Full transcript │
                                             ├──────────────────┤
                                             │  Deterministic   │
                                             │  metadata checks │
                                             │  (call time,     │
                                             │   debt amount)   │
                                             └──────────────────┘
                                                          │
                                                    web/index.html
                                                    (static SPA)
```

## API

### `POST /audit`

**Request:**
```json
{
  "transcript": {
    "transcript_id": "tx_001_clean",
    "turns": [
      {"speaker": "agent", "text": "Hello..."},
      {"speaker": "consumer", "text": "Hi..."}
    ]
  },
  "metadata": {
    "call_timestamp_local": "2026-04-15T14:30:00",
    "consumer_timezone": "America/New_York",
    "call_attempts_7day": 1,
    "validation_notice_sent": true,
    "debt_amount_original": 1247.50,
    "debt_amount_claimed": 1247.50
  }
}
```

**Response:**
```json
{
  "overall_score": "PASS",
  "compliance_score": 100.0,
  "total_rules": 12,
  "total_passed": 12,
  "total_failed": 0,
  "autofail_violations": [],
  "is_compliant": true,
  "summary": "The transcript shows full compliance...",
  "evaluation_time_ms": 3200,
  "rule_results": [...]
}
```

## LLM Providers

Supported providers (set `LLM_PROVIDER` in `.env`):

- `anthropic` — Claude (default)
- `openai` — GPT-4o
- `openrouter` — Any model via OpenRouter

## Deployment

A `Dockerfile` is included for **Hugging Face Spaces** deployment:

```bash
docker build -t scrutiny .
docker run -p 7860:7860 --env-file .env scrutiny
```

**Live demo:** [https://huggingface.co/spaces/ree2raz/Scrutiny](https://huggingface.co/spaces/ree2raz/Scrutiny)

## License

Apache 2.0 — see `LICENSE`.

## Disclaimer

Scrutiny is for **evaluation, research, and compliance monitoring** purposes. It is not legal advice. Always consult qualified counsel for FDCPA / Reg F compliance decisions.

---

**Need a custom rubric for your compliance workflow?** Pilot engagements available — book a call at [cal.com/ree2raz/quick-chat](https://cal.com/ree2raz/quick-chat).
