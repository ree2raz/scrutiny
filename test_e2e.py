"""
End-to-end smoke test for Scrutiny.

Uses a mock LLM client so it can run without API keys.
Verifies that all 5 synthetic transcripts parse correctly and that
the evaluator produces structurally valid ComplianceReports.
"""

from __future__ import annotations

import json
import pathlib
import sys

from fdcpa_audit.evaluator import evaluate_audit_request
from fdcpa_audit.llm import LLMClient
from fdcpa_audit.models import AuditRequest, ComplianceReport, Transcript, TranscriptMetadata


class MockLLMClient(LLMClient):
    """A mock LLM that returns canned compliance results based on transcript ID."""

    def __init__(self):
        self.model = "mock"

    def complete(self, system: str, user: str) -> str:
        # Extract transcript ID from the formatted user message
        transcript_id = "unknown"
        for line in user.splitlines():
            if line.startswith("TRANSCRIPT ID:"):
                transcript_id = line.split(":", 1)[1].strip()
                break

        # Determine expected autofail violations per transcript
        autofails = {
            "tx_001_clean": [],
            "tx_002_no_miranda": ["FDCPA-001"],
            "tx_003_voicemail": ["FDCPA-004"],
            "tx_004_cease_desist": ["FDCPA-009"],
            "tx_005_harassment": ["FDCPA-005", "FDCPA-007"],
        }.get(transcript_id, [])

        # Determine expected non-autofail failures per transcript
        extra_fails = {
            "tx_003_voicemail": ["FDCPA-011"],
            "tx_005_harassment": ["FDCPA-002", "FDCPA-008"],
        }.get(transcript_id, [])

        rule_results = []
        rubric_path = pathlib.Path(__file__).parent / "fdcpa_rubric.json"
        with rubric_path.open("r", encoding="utf-8") as f:
            rubric = json.load(f)

        for rule in rubric["rules"]:
            rid = rule["rule_id"]
            if rid == "FDCPA-003":
                # Skip in LLM response — handled deterministically
                continue
            failed = rid in autofails or rid in extra_fails
            verdict = "fail" if failed else "pass"
            points_earned = 0 if failed else rule["points"]
            evidence = (
                "Violation detected in transcript."
                if failed
                else "Compliant behavior observed."
            )
            severity = (
                "critical" if (failed and rule["is_autofail"]) else
                ("major" if failed else "none")
            )
            rule_results.append({
                "rule_id": rid,
                "rule_name": rule["rule_name"],
                "category": rule["category"],
                "verdict": verdict,
                "reasoning": f"Mock evaluation for {rid} on {transcript_id}.",
                "evidence_quote": evidence,
                "is_autofail": rule["is_autofail"],
                "points": rule["points"],
                "points_earned": points_earned,
                "legal_basis": rule.get("legal_basis"),
                "severity": severity,
            })

        total_points = sum(r["points"] for r in rule_results)
        points_earned = sum(r["points_earned"] for r in rule_results)
        score = round(points_earned / total_points * 100, 1) if total_points else 0.0
        is_compliant = len(autofails) == 0

        summary = (
            f"Mock evaluation for '{transcript_id}'. "
            f"Score: {score}%. Autofail violations: {autofails or 'none'}."
        )

        return json.dumps({
            "rule_results": rule_results,
            "summary": summary,
        })


def load_transcript_and_meta(name: str) -> AuditRequest:
    base = pathlib.Path(__file__).parent / "transcripts"
    with (base / f"{name}.json").open("r", encoding="utf-8") as f:
        transcript = Transcript(**json.load(f))
    with (base / f"{name}_meta.json").open("r", encoding="utf-8") as f:
        metadata = TranscriptMetadata(**json.load(f))
    return AuditRequest(transcript=transcript, metadata=metadata)


def test_all_transcripts() -> None:
    names = [
        "tx_001_clean",
        "tx_002_no_miranda",
        "tx_003_voicemail",
        "tx_004_cease_desist",
        "tx_005_harassment",
    ]

    for name in names:
        print(f"Testing {name} ... ", end="")
        request = load_transcript_and_meta(name)
        report = evaluate_audit_request(request, llm_client=MockLLMClient())

        # Structural validations
        assert report.transcript_id == request.transcript.transcript_id
        assert len(report.rule_results) == 12
        assert report.total_rules == 12
        assert report.total_passed + report.total_failed + report.total_not_evaluable == 12
        assert 0 <= report.compliance_score <= 100
        assert isinstance(report.is_compliant, bool)
        assert report.summary
        assert report.evaluation_time_ms >= 0
        assert report.overall_score

        # Ground-truth checks
        expected_autofails = {
            "tx_001_clean": [],
            "tx_002_no_miranda": ["FDCPA-001"],
            "tx_003_voicemail": ["FDCPA-004"],
            "tx_004_cease_desist": ["FDCPA-009"],
            "tx_005_harassment": ["FDCPA-005", "FDCPA-007"],
        }.get(name, [])

        assert report.autofail_violations == expected_autofails, (
            f"{name}: expected autofails {expected_autofails}, got {report.autofail_violations}"
        )

        if name == "tx_001_clean":
            assert report.is_compliant, "tx_001_clean should be compliant"

        if expected_autofails:
            assert not report.is_compliant, f"{name} should not be compliant"

        # Check deterministic call time evaluation
        call_time_result = next(r for r in report.rule_results if r.rule_id == "FDCPA-003")
        assert call_time_result.verdict == "pass", f"{name}: call time should pass"

        print(f"OK (score={report.compliance_score}%, autofails={report.autofail_violations or 'none'})")


def test_call_time_violation() -> None:
    """Test that a late-night call fails the deterministic check."""
    print("Testing late-night call time violation ... ", end="")
    request = load_transcript_and_meta("tx_001_clean")
    request.metadata.call_timestamp_local = "2026-04-15T23:30:00"
    request.metadata.consumer_timezone = "America/New_York"

    report = evaluate_audit_request(request, llm_client=MockLLMClient())

    call_time_result = next(r for r in report.rule_results if r.rule_id == "FDCPA-003")
    assert call_time_result.verdict == "fail", "Late-night call should fail"
    assert call_time_result.severity == "critical"
    assert not report.is_compliant, "Late-night call should make non-compliant"
    print("OK")


def test_missing_metadata() -> None:
    """Test that missing metadata yields not_evaluable for call time."""
    print("Testing missing metadata ... ", end="")
    request = load_transcript_and_meta("tx_001_clean")
    request.metadata.call_timestamp_local = None
    request.metadata.consumer_timezone = None

    report = evaluate_audit_request(request, llm_client=MockLLMClient())

    call_time_result = next(r for r in report.rule_results if r.rule_id == "FDCPA-003")
    assert call_time_result.verdict == "not_evaluable"
    print("OK")


if __name__ == "__main__":
    print("=" * 60)
    print("Scrutiny — End-to-End Smoke Test")
    print("=" * 60)
    try:
        test_all_transcripts()
        test_call_time_violation()
        test_missing_metadata()
        print("=" * 60)
        print("All tests PASSED.")
        sys.exit(0)
    except AssertionError as exc:
        print("=" * 60)
        print(f"Some tests FAILED: {exc}")
        sys.exit(1)
