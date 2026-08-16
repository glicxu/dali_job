from app.modules.evaluation.privacy import redact_candidate_text, redact_value, sensitive_categories


def test_candidate_redaction_removes_contact_channels_without_removing_evidence() -> None:
    source = (
        "Jane Candidate\n"
        "jane.candidate@example.com | +1 (415) 555-1212\n"
        "https://www.linkedin.com/in/jane-candidate\n"
        "Built production Python APIs used by 20 teams."
    )

    redacted = redact_candidate_text(source)

    assert "jane.candidate@example.com" not in redacted
    assert "415" not in redacted
    assert "linkedin.com" not in redacted
    assert "Built production Python APIs used by 20 teams." in redacted
    assert sensitive_categories(redacted) == []
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_URL]" in redacted


def test_nested_export_values_are_redacted() -> None:
    payload = {
        "comment": "Verify with reviewer@example.com",
        "facts": ["Portfolio: https://example.com/private", "Phone 212-555-0100"],
        "count": 3,
    }

    redacted = redact_value(payload)

    assert redacted == {
        "comment": "Verify with [REDACTED_EMAIL]",
        "facts": ["Portfolio: [REDACTED_URL]", "Phone [REDACTED_PHONE]"],
        "count": 3,
    }
