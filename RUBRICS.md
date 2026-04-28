# Rubric Packs

Scrutiny is built around regulation-specific rubric packs. Each pack contains evaluable rules, legal citations, pass/fail examples, and metadata cross-checks.

## Available Now

### FDCPA / Reg F — Debt Collection Calls
- **Rules:** 12
- **Status:** Open source, included in every installation
- **Coverage:** Mini-Miranda, validation notice, call time, third-party disclosure, harassment, false representation, false threats, unfair practices, cease-and-desist, dispute handling, voicemail safe harbor, attorney representation
- **Legal basis:** 15 U.S.C. § 1692 et seq., 12 CFR Part 1006
- **Evaluability:** Transcript + metadata hybrid
- **Maturity:** Production-ready with synthetic test suite

## Coming Soon

| Pack | Regulation | Estimated Rules | Domain |
|---|---|---|---|
| FINRA 3110 | FINRA Rule 3110 (Supervision) | 8–10 | Broker-dealer calls |
| FTC Section 5 | 15 U.S.C. § 45 (Unfair/Deceptive Acts) | 10–12 | Direct sales / telemarketing |
| TCPA | 47 U.S.C. § 227 | 6–8 | Robocall / SMS consent |
| UDAAP | Dodd-Frank § 1031 / 12 CFR Part 1090 | 8–10 | Consumer lending calls |
| HIPAA | 45 CFR Part 164 | 10–12 | Healthcare collections |
| GDPR Art. 5–7 | Regulation (EU) 2016/679 | 8–10 | EU consumer outreach |
| PCI-DSS | PCI SSC Standard v4.0 | 6–8 | Payment card phone handling |
| FCRA | 15 U.S.C. § 1681 | 8–10 | Credit reporting disputes |

## Custom Rubric Development

Need a rubric for a regulation not listed here? We build custom packs for:

- Industry-specific compliance workflows
- Internal policy enforcement (custom scripts, not just statutes)
- Multi-jurisdiction bundles (e.g., FDCPA + state mini-FDCPA)
- Localization (non-US regulations with local legal review)

**Contact:** ree2raz@proton.me

## Rubric Specification

Each rubric pack is a JSON file with this structure:

```json
{
  "title": "...",
  "version": "1.0.0",
  "legal_basis": "...",
  "rules": [
    {
      "rule_id": "REG-001",
      "rule_name": "...",
      "description": "...",
      "example": "...",
      "category": "...",
      "is_autofail": false,
      "points": 10,
      "legal_basis": "...",
      "evaluability": "transcript|metadata|transcript_and_metadata",
      "violation_catalog_id": "V-001"
    }
  ]
}
```

See `fdcpa_rubric.json` for a complete working example.
