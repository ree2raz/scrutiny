"""
Pydantic models for FDCPA/Reg F call transcript compliance audit.

These models enforce the schema at every boundary: LLM output gets validated
on ingestion, not downstream. If the LLM produces invalid JSON, it fails here
with a clear error.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SubCondition(BaseModel):
    """One part of a composite rule. Combined via AND/OR with siblings."""

    condition: str = Field(description="What this sub-condition checks.")
    operator: Literal["AND", "OR"] = Field(
        description="How this combines with other sub-conditions."
    )


class Rule(BaseModel):
    """A single evaluable rule from the FDCPA rubric."""

    rule_id: str = Field(description="Unique identifier, e.g. 'FDCPA-001'.")
    rule_name: str = Field(description="Short human-readable name.")
    description: str = Field(description="Full evaluation criteria.")
    example: str | None = Field(
        default=None, description="Optional example of pass/fail."
    )
    category: str = Field(description="Grouping category.")
    is_autofail: bool = Field(
        description="True if failing this rule fails the entire evaluation."
    )
    points: int = Field(ge=0, description="Point value.")
    legal_basis: str | None = Field(
        default=None, description="Statutory or regulatory citation."
    )
    evaluability: Literal["transcript", "metadata", "transcript_and_metadata"] = Field(
        default="transcript",
        description="How this rule is evaluated.",
    )
    violation_catalog_id: str | None = Field(
        default=None, description="Mapping to the violation catalog."
    )
    sub_conditions: list[SubCondition] | None = Field(
        default=None,
        description="For composite rules only.",
    )


class CompiledRubric(BaseModel):
    """A validated set of rules ready for evaluation."""

    title: str
    version: str
    legal_basis: str | None = None
    compiled_at: str
    rules: list[Rule]


class Turn(BaseModel):
    """One speaker turn in a call transcript."""

    speaker: Literal["agent", "consumer", "system", "unknown", "third_party"]
    text: str = Field(description="Transcribed text for this turn.")
    timestamp: str | None = Field(
        default=None, description="Optional timestamp for this turn."
    )


class Transcript(BaseModel):
    """A redacted collections call transcript to evaluate."""

    transcript_id: str
    turns: list[Turn] = Field(min_length=1)


class TranscriptMetadata(BaseModel):
    """Metadata sidecar for a call transcript.

    Fields the LLM cannot extract from text alone.
    """

    call_timestamp_local: str | None = Field(
        default=None, description="ISO 8601 timestamp of the call in local time."
    )
    consumer_timezone: str | None = Field(
        default=None, description="IANA timezone of the consumer, e.g. America/New_York."
    )
    call_attempts_7day: int | None = Field(
        default=None, ge=0, description="Number of call attempts in the past 7 days."
    )
    validation_notice_sent: bool | None = Field(
        default=None, description="Whether a written validation notice was sent."
    )
    validation_notice_date: str | None = Field(
        default=None, description="Date the validation notice was sent."
    )
    attorney_on_record: bool | None = Field(
        default=None, description="Whether the consumer has retained counsel for this debt."
    )
    cease_desist_on_file: bool | None = Field(
        default=None, description="Whether a written cease-and-desist request is on file."
    )
    dispute_on_file: bool | None = Field(
        default=None, description="Whether a written dispute is on file."
    )
    debt_amount_original: float | None = Field(
        default=None, ge=0, description="Original debt amount per the agreement."
    )
    debt_amount_claimed: float | None = Field(
        default=None, ge=0, description="Debt amount currently claimed by the collector."
    )
    call_direction: Literal["inbound", "outbound"] | None = Field(
        default=None, description="Direction of the call."
    )
    extra: dict[str, str] | None = Field(
        default=None, description="Additional metadata fields."
    )


class AuditRequest(BaseModel):
    """Request body for the /audit endpoint."""

    transcript: Transcript
    metadata: TranscriptMetadata = Field(default_factory=TranscriptMetadata)
    demo: bool = Field(
        default=False,
        description="If True, use cached demo response instead of calling an LLM.",
    )
    provider_api_key: str | None = Field(
        default=None,
        description="Visitor-provided API key. Overrides server config for this request.",
    )
    provider: Literal["huggingface", "anthropic", "openai", "openrouter"] | None = Field(
        default=None,
        description="Override LLM provider for this request.",
    )


class RuleResult(BaseModel):
    """Result of evaluating one rule against a transcript + metadata."""

    rule_id: str
    rule_name: str
    category: str
    verdict: Literal["pass", "fail", "not_evaluable"]
    reasoning: str = Field(description="Why the rule passed, failed, or could not be evaluated.")
    evidence_quote: str = Field(
        description="Verbatim text from the transcript supporting the verdict."
    )
    is_autofail: bool
    points: int
    points_earned: int = Field(ge=0, description="Points earned (0 if fail, full points if pass).")
    legal_basis: str | None = Field(default=None, description="Statutory citation.")
    severity: Literal["critical", "major", "minor", "none"] | None = Field(
        default=None, description="Severity classification."
    )


class ComplianceReport(BaseModel):
    """Full compliance evaluation results for one transcript."""

    transcript_id: str
    evaluated_at: datetime = Field(default_factory=datetime.now)
    llm_provider: str
    llm_model: str
    overall_score: str = Field(description="Human-readable overall score line.")
    rule_results: list[RuleResult]
    total_rules: int
    total_passed: int
    total_failed: int
    total_not_evaluable: int
    total_points: int
    points_earned: int
    compliance_score: float = Field(
        ge=0.0, le=100.0,
        description="Percentage of points earned."
    )
    is_compliant: bool = Field(
        description="True if no autofail rules failed and score >= threshold."
    )
    autofail_violations: list[str] = Field(
        default_factory=list,
        description="Rule IDs of any autofail rules that failed."
    )
    summary: str = Field(description="Narrative summary of findings.")
    evaluation_time_ms: int = Field(description="Time spent evaluating in milliseconds.")


class ViolationSummary(BaseModel):
    """Simplified violation object for API responses."""

    rule_id: str
    verdict: Literal["pass", "fail", "not_evaluable"]
    evidence_quote: str
    legal_basis: str | None = None
    severity: Literal["critical", "major", "minor", "none"] | None = None
