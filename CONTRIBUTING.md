# Contributing to Scrutiny

Thank you for your interest in expanding Scrutiny's coverage. We accept rubric contributions for new regulations, jurisdictions, and industries.

## What We're Looking For

- **New regulation rubrics** — FINRA, HIPAA, GDPR, state-specific mini-FDCPAs, etc.
- **Rule refinements** — Better examples, clearer descriptions, corrected legal citations
- **Transcript contributions** — Synthetic test transcripts for new violation types
- **Localization** — Non-US regulations with local legal review

## What You Get

- **Credit** in the rubric pack metadata and release notes
- **Co-authorship** on the regulation pack you build
- **Early access** to platform features as we expand

## What We Get

- **Domain expertise** we don't have in-house
- **Broader platform coverage** without hiring regulatory counsel for every jurisdiction
- **Community-validated rules** before they go into production

## How to Contribute a Rubric

### 1. Propose the regulation
Open a GitHub issue with:
- Regulation name and legal citation
- Estimated number of rules
- Whether you have legal/domain expertise in this area
- Target industry and geography

### 2. Draft the rubric
Follow the format in `fdcpa_rubric.json`:

```json
{
  "title": "Your Regulation Name",
  "version": "1.0.0",
  "legal_basis": "Statutory citation",
  "compiled_at": "YYYY-MM-DD",
  "rules": [
    {
      "rule_id": "REG-001",
      "rule_name": "Rule Name",
      "description": "Evaluation criteria — must be checkable by an LLM reading transcript text",
      "example": "PASS: ... FAIL: ...",
      "category": "Category",
      "is_autofail": false,
      "points": 10,
      "legal_basis": "Statutory citation",
      "evaluability": "transcript|metadata|transcript_and_metadata",
      "violation_catalog_id": "V-001"
    }
  ]
}
```

Requirements:
- Each rule must be **evaluable by an LLM reading transcript text** (or deterministically from metadata)
- Include **verbatim pass/fail examples**
- Cite **specific statutory or regulatory sections**
- Flag **autofail rules** that fail the entire evaluation
- Set **point values** that sum to a meaningful 0-100 scale

### 3. Add test transcripts
Provide 3–5 synthetic transcripts:
- At least one **clean** (all rules pass)
- One per **planted violation** for ground-truth testing
- Raw `.md` + redacted `.json` + metadata `.json` (see `transcripts/` for examples)

### 4. Submit a PR
- Title: `Rubric: [Regulation Name]`
- Include the rubric JSON, test transcripts, and a brief legal basis writeup
- Tag the issue you opened in step 1

## Review Process

1. **Legal sanity check** — We verify citations and rule logic against primary sources
2. **Evaluability test** — We run the rubric against your transcripts with Claude/GPT-4o
3. **Edge case audit** — We test ambiguous scenarios to ensure the rules don't over-flag
4. **Merge** — Approved rubrics ship in the next minor release

## Contributor License Agreement

By submitting a rubric, you agree that:
- The content is your original work or properly licensed
- You grant Scrutiny a perpetual license to distribute and modify the rubric
- You retain attribution credit in perpetuity

## Questions?

Open an issue or email ree2raz@proton.me.
