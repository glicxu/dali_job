from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ExtractionResultLike(Protocol):
    focused_text: str
    sections: dict[str, list[str]]
    confidence: float
    extraction_method: str


@dataclass(frozen=True)
class ExtractionQualityMetrics:
    source_name: str
    extraction_method: str
    confidence: float
    required_content_recall: float
    noise_exclusion_rate: float
    expected_section_recall: float

    @property
    def passed(self) -> bool:
        return (
            self.required_content_recall == 1.0
            and self.noise_exclusion_rate == 1.0
            and self.expected_section_recall == 1.0
        )


def measure_extraction_quality(
    result: ExtractionResultLike,
    *,
    source_name: str,
    required_terms: tuple[str, ...] = (),
    excluded_terms: tuple[str, ...] = (),
    expected_sections: tuple[str, ...] = (),
) -> ExtractionQualityMetrics:
    focused_lower = result.focused_text.lower()
    required_hits = sum(term.lower() in focused_lower for term in required_terms)
    excluded_hits = sum(term.lower() not in focused_lower for term in excluded_terms)
    section_hits = sum(bool(result.sections.get(section)) for section in expected_sections)
    return ExtractionQualityMetrics(
        source_name=source_name,
        extraction_method=result.extraction_method,
        confidence=result.confidence,
        required_content_recall=required_hits / len(required_terms) if required_terms else 1.0,
        noise_exclusion_rate=excluded_hits / len(excluded_terms) if excluded_terms else 1.0,
        expected_section_recall=section_hits / len(expected_sections) if expected_sections else 1.0,
    )
