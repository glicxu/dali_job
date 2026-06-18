from __future__ import annotations

from app.modules.profiles.models import default_resume_data
from app.modules.profiles.resume_import import SYSTEM_PROMPT, redact_resume_personal_info
from app.modules.profiles.schemas import ResumeData


def test_resume_data_schema_excludes_personal_contact_fields() -> None:
    payload = ResumeData(
        headline="Backend Engineer",
        summary="Builds APIs.",
        skills=["Python"],
    ).model_dump()

    assert "name" not in payload
    assert "contact" not in payload
    assert "links" not in payload
    assert "target_locations" not in payload
    assert "name" not in default_resume_data()
    assert "contact" not in default_resume_data()


def test_resume_redaction_removes_header_pii_before_ai_parsing() -> None:
    text = """
    Jane Example
    jane@example.com | 555-123-4567 | Denver, CO | https://janesite.example

    Summary
    Backend engineer with Python and FastAPI experience.

    Experience
    Software Engineer at Example Co
    Built APIs for customer workflows.
    """

    redacted = redact_resume_personal_info(text)

    assert "Jane Example" not in redacted
    assert "jane@example.com" not in redacted
    assert "555-123-4567" not in redacted
    assert "Denver, CO" not in redacted
    assert "https://janesite.example" not in redacted
    assert "Backend engineer with Python and FastAPI experience." in redacted
    assert "Software Engineer at Example Co" in redacted


def test_resume_redaction_does_not_change_resume_without_detected_pii() -> None:
    text = "Summary\nBackend engineer with Python.\n\nSkills\nPython\nFastAPI"

    redacted = redact_resume_personal_info(text)

    assert redacted == text


def test_resume_parse_prompt_requires_generated_headline_and_summary() -> None:
    assert 'Generate "headline" and "summary"' in SYSTEM_PROMPT
    assert "12 words or fewer" in SYSTEM_PROMPT
    assert "2-3 short sentences" in SYSTEM_PROMPT
    assert "unsupported claims" in SYSTEM_PROMPT
