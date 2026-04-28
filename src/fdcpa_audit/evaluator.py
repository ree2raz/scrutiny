"""
FDCPA/Reg F transcript evaluator.

Dual-path evaluation:
  1. Deterministic checks for metadata-only rules (currently FDCPA-003 call time).
  2. Single LLM call for all transcript-evaluable rules, with metadata included
     as cross-validation context.

This works because call transcripts are short (~300-800 words) and fit in a
single LLM context window.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime
from time import perf_counter

from fdcpa_audit.llm import LLMClient, get_llm_client
from fdcpa_audit.models import (
    AuditRequest,
    ComplianceReport,
    CompiledRubric,
    RuleResult,
    TranscriptMetadata,
)


def _load_prompt(path: pathlib.Path | None = None) -> str:
    if path is None:
        path = (
            pathlib.Path(__file__).with_suffix("").parent
            / "prompts"
            / "evaluate_transcript.md"
        )
    return path.read_text()


def _load_rubric(path: pathlib.Path | None = None) -> CompiledRubric:
    if path is None:
        path = pathlib.Path(__file__).with_suffix("").parent.parent.parent / "fdcpa_rubric.json"
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return CompiledRubric(**data)


def _format_transcript(transcript) -> str:
    lines = []
    lines.append(f"TRANSCRIPT ID: {transcript.transcript_id}")
    lines.append("---")
    for i, turn in enumerate(transcript.turns, 1):
        speaker = turn.speaker.upper()
        ts = f" [{turn.timestamp}]" if turn.timestamp else ""
        lines.append(f"{i}.{ts} {speaker}: {turn.text}")
    return "\n".join(lines)


def _format_metadata_context(metadata: TranscriptMetadata) -> str:
    """Format metadata into a string for inclusion in the LLM prompt."""
    lines = []
    if metadata.call_timestamp_local:
        lines.append(f"call_timestamp_local: {metadata.call_timestamp_local}")
    if metadata.consumer_timezone:
        lines.append(f"consumer_timezone: {metadata.consumer_timezone}")
    if metadata.call_attempts_7day is not None:
        lines.append(f"call_attempts_7day: {metadata.call_attempts_7day}")
    if metadata.validation_notice_sent is not None:
        lines.append(f"validation_notice_sent: {metadata.validation_notice_sent}")
    if metadata.validation_notice_date:
        lines.append(f"validation_notice_date: {metadata.validation_notice_date}")
    if metadata.attorney_on_record is not None:
        lines.append(f"attorney_on_record: {metadata.attorney_on_record}")
    if metadata.cease_desist_on_file is not None:
        lines.append(f"cease_desist_on_file: {metadata.cease_desist_on_file}")
    if metadata.dispute_on_file is not None:
        lines.append(f"dispute_on_file: {metadata.dispute_on_file}")
    if metadata.debt_amount_original is not None:
        lines.append(f"debt_amount_original: {metadata.debt_amount_original}")
    if metadata.debt_amount_claimed is not None:
        lines.append(f"debt_amount_claimed: {metadata.debt_amount_claimed}")
    if metadata.call_direction:
        lines.append(f"call_direction: {metadata.call_direction}")
    if metadata.extra:
        for k, v in metadata.extra.items():
            lines.append(f"{k}: {v}")
    if not lines:
        lines.append("No metadata provided.")
    return "\n".join(lines)


def _check_call_time(metadata: TranscriptMetadata) -> RuleResult:
    """Deterministic check for FDCPA-003 (Call Time Compliance)."""
    rule = RuleResult(
        rule_id="FDCPA-003",
        rule_name="Call Time Compliance",
        category="Time",
        verdict="not_evaluable",
        reasoning="",
        evidence_quote="N/A",
        is_autofail=True,
        points=10,
        points_earned=0,
        legal_basis="15 U.S.C. § 1692c(a)(1); 12 CFR § 1006.14(b)",
        severity="none",
    )

    if not metadata.call_timestamp_local or not metadata.consumer_timezone:
        rule.reasoning = (
            "Cannot evaluate: call_timestamp_local or consumer_timezone is missing from metadata."
        )
        rule.points_earned = 0
        return rule

    try:
        # Parse ISO 8601 timestamp (already in local time)
        ts = datetime.fromisoformat(metadata.call_timestamp_local.replace("Z", "+00:00"))
        hour = ts.hour
    except Exception as exc:
        rule.reasoning = f"Cannot evaluate: failed to parse call_timestamp_local ({exc})."
        rule.points_earned = 0
        return rule

    # Permitted hours: 8:00 AM to 9:00 PM (21:00) inclusive of 8, exclusive of 21
    if 8 <= hour < 21:
        rule.verdict = "pass"
        rule.reasoning = (
            f"Call placed at {hour:02d}:{ts.minute:02d} "
            f"in {metadata.consumer_timezone}. This is within the permitted 8:00 AM – 9:00 PM window."
        )
        rule.points_earned = rule.points
        rule.severity = "none"
    else:
        rule.verdict = "fail"
        rule.reasoning = (
            f"Call placed at {hour:02d}:{ts.minute:02d} "
            f"in {metadata.consumer_timezone}. This is outside the permitted 8:00 AM – 9:00 PM window."
        )
        rule.points_earned = 0
        rule.severity = "critical"

    return rule


def evaluate_audit_request(
    request: AuditRequest,
    llm_client: LLMClient | None = None,
    system_prompt: str | None = None,
) -> ComplianceReport:
    """Evaluate an audit request (transcript + metadata) against the FDCPA rubric.

    Returns a fully-populated ComplianceReport with per-rule results,
    aggregate scores, and a narrative summary.
    """
    start_time = perf_counter()

    # Use visitor-provided key if present
    if request.provider_api_key:
        client = get_llm_client(
            provider=request.provider,
            api_key=request.provider_api_key,
        )
    else:
        client = llm_client or get_llm_client()

    # 1. Deterministic checks for metadata-only rules
    deterministic_results: dict[str, RuleResult] = {}
    deterministic_results["FDCPA-003"] = _check_call_time(request.metadata)

    # 2. LLM evaluation for all transcript-evaluable rules
    prompt_template = system_prompt or _load_prompt()
    metadata_ctx = _format_metadata_context(request.metadata)
    system = prompt_template.replace("{metadata_context}", metadata_ctx)
    user = _format_transcript(request.transcript)

    raw = client.complete(system=system, user=user)

    # Strip markdown fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```")
        cleaned = cleaned.strip()

    parsed = json.loads(cleaned)
    llm_results = [RuleResult(**r) for r in parsed["rule_results"]]
    summary = parsed["summary"]

    # 3. Merge results: deterministic overrides for metadata-only rules
    rule_results: list[RuleResult] = []
    for lr in llm_results:
        if lr.rule_id in deterministic_results:
            # Use deterministic result instead of LLM's placeholder
            rule_results.append(deterministic_results[lr.rule_id])
        else:
            rule_results.append(lr)

    # Ensure FDCPA-003 is present even if LLM omitted it
    if "FDCPA-003" not in {r.rule_id for r in rule_results}:
        rule_results.insert(2, deterministic_results["FDCPA-003"])

    total_rules = len(rule_results)
    total_passed = sum(1 for r in rule_results if r.verdict == "pass")
    total_failed = sum(1 for r in rule_results if r.verdict == "fail")
    total_not_evaluable = sum(1 for r in rule_results if r.verdict == "not_evaluable")
    total_points = sum(r.points for r in rule_results)
    points_earned = sum(r.points_earned for r in rule_results)
    compliance_score = (points_earned / total_points * 100) if total_points > 0 else 0.0

    autofail_violations = [
        r.rule_id for r in rule_results if r.is_autofail and r.verdict == "fail"
    ]
    is_compliant = len(autofail_violations) == 0

    af_count = len(autofail_violations)
    overall_score = (
        "PASS" if is_compliant else f"FAIL — {af_count} autofail violation{'s' if af_count != 1 else ''}"
    )

    elapsed_ms = int((perf_counter() - start_time) * 1000)

    return ComplianceReport(
        transcript_id=request.transcript.transcript_id,
        evaluated_at=datetime.now(),
        llm_provider=client.__class__.__name__,
        llm_model=getattr(client, "model", "unknown"),
        overall_score=overall_score,
        rule_results=rule_results,
        total_rules=total_rules,
        total_passed=total_passed,
        total_failed=total_failed,
        total_not_evaluable=total_not_evaluable,
        total_points=total_points,
        points_earned=points_earned,
        compliance_score=round(compliance_score, 1),
        is_compliant=is_compliant,
        autofail_violations=autofail_violations,
        summary=summary,
        evaluation_time_ms=elapsed_ms,
    )
