from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

CANONICALIZATION_VERSION = "canonical-text.v2"
SPAN_POLICY_VERSION = "evidence-spans.v1"
MAX_SPAN_CHARS = 1_200

_BULLET_RE = re.compile(r"^(?:[-*•▪◦]|\d{1,3}[.)])\s+")
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+")
_NON_ID_RE = re.compile(r"[^a-z0-9]+")
_KNOWN_SECTIONS = {
    "summary": "summary",
    "profile": "summary",
    "professional summary": "summary",
    "experience": "experience",
    "work experience": "experience",
    "professional experience": "experience",
    "employment": "experience",
    "projects": "projects",
    "skills": "skills",
    "technical skills": "skills",
    "education": "education",
    "certifications": "certifications",
    "publications": "publications",
    "awards": "awards",
    "languages": "languages",
    "volunteer": "volunteer",
    "volunteer experience": "volunteer",
    "requirements": "requirements",
    "required qualifications": "requirements",
    "minimum qualifications": "requirements",
    "preferred qualifications": "preferred_requirements",
    "qualifications": "requirements",
    "responsibilities": "responsibilities",
    "duties": "responsibilities",
    "what you will do": "responsibilities",
    "compensation": "compensation",
    "salary": "compensation",
    "benefits": "benefits",
    "location": "location",
    "about the company": "company",
}


@dataclass(frozen=True)
class EvidenceSpan:
    span_id: str
    section: str
    start_utf8_byte: int
    end_utf8_byte: int
    excerpt: str


def canonicalize_text(value: str) -> str:
    """Apply narrow Unicode normalization plus known job-board mojibake repair."""
    normalized = unicodedata.normalize("NFC", value)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\x00", "")
    replacements = {
        "â€™": "’", "â€˜": "‘", "â€œ": "“", "â€": "”",
        "â€”": "—", "â€“": "–", "â€¢": "•", "Â ": " ",
    }
    for damaged, repaired in replacements.items():
        normalized = normalized.replace(damaged, repaired)
    return normalized


def build_evidence_spans(
    canonical_text: str,
    *,
    source_prefix: str,
    max_span_chars: int = MAX_SPAN_CHARS,
) -> list[EvidenceSpan]:
    if canonical_text != canonicalize_text(canonical_text):
        raise ValueError(f"Evidence spans require {CANONICALIZATION_VERSION} input.")
    if max_span_chars < 100:
        raise ValueError("max_span_chars must be at least 100.")
    safe_prefix = _slug(source_prefix) or "source"
    ranges = _semantic_ranges(canonical_text)
    spans: list[EvidenceSpan] = []
    section_ordinals: dict[str, int] = {}
    for start, end, section in ranges:
        for chunk_start, chunk_end in _bounded_ranges(
            canonical_text,
            start,
            end,
            max_span_chars=max_span_chars,
        ):
            excerpt = canonical_text[chunk_start:chunk_end]
            if not excerpt:
                continue
            ordinal = section_ordinals.get(section, 0) + 1
            section_ordinals[section] = ordinal
            spans.append(
                EvidenceSpan(
                    span_id=f"{safe_prefix}:{section}:{ordinal:04d}",
                    section=section,
                    start_utf8_byte=len(canonical_text[:chunk_start].encode("utf-8")),
                    end_utf8_byte=len(canonical_text[:chunk_end].encode("utf-8")),
                    excerpt=excerpt,
                )
            )
    return spans


def _semantic_ranges(text: str) -> list[tuple[int, int, str]]:
    ranges: list[tuple[int, int, str]] = []
    ordinary_start: int | None = None
    ordinary_end: int | None = None
    current_section = "general"

    def flush_ordinary() -> None:
        nonlocal ordinary_start, ordinary_end
        if ordinary_start is not None and ordinary_end is not None:
            ranges.append((ordinary_start, ordinary_end, current_section))
        ordinary_start = None
        ordinary_end = None

    for match in re.finditer(r"[^\n]*(?:\n|$)", text):
        raw_line = match.group(0)
        if not raw_line:
            continue
        content_end = match.end() - (1 if raw_line.endswith("\n") else 0)
        line = text[match.start():content_end]
        leading = len(line) - len(line.lstrip())
        trailing = len(line.rstrip())
        start = match.start() + leading
        end = match.start() + trailing
        stripped = line.strip()
        if not stripped:
            flush_ordinary()
            continue

        heading = _heading_section(stripped)
        is_bullet = bool(_BULLET_RE.match(stripped))
        is_table = stripped.count("|") >= 2
        if heading is not None:
            flush_ordinary()
            current_section = heading
            ranges.append((start, end, current_section))
        elif is_bullet or is_table:
            flush_ordinary()
            ranges.append((start, end, current_section))
        else:
            if ordinary_start is None:
                ordinary_start = start
            ordinary_end = end
    flush_ordinary()
    return ranges


def _heading_section(value: str) -> str | None:
    candidate = _MARKDOWN_HEADING_RE.sub("", value).rstrip(":").strip()
    normalized = re.sub(r"\s+", " ", candidate).lower()
    if normalized in _KNOWN_SECTIONS:
        return _KNOWN_SECTIONS[normalized]
    looks_like_heading = (
        len(candidate) <= 60
        and len(candidate.split()) <= 7
        and (
            bool(_MARKDOWN_HEADING_RE.match(value))
            or value.endswith(":")
            or (any(char.isalpha() for char in candidate) and candidate.upper() == candidate)
        )
    )
    return _slug(candidate) if looks_like_heading else None


def _bounded_ranges(
    text: str,
    start: int,
    end: int,
    *,
    max_span_chars: int,
) -> list[tuple[int, int]]:
    chunks: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > max_span_chars:
        limit = cursor + max_span_chars
        split = max(text.rfind("\n", cursor, limit + 1), text.rfind(" ", cursor, limit + 1))
        if split <= cursor + max_span_chars // 2:
            split = limit
        chunk_end = split
        while chunk_end > cursor and text[chunk_end - 1].isspace():
            chunk_end -= 1
        if chunk_end > cursor:
            chunks.append((cursor, chunk_end))
        cursor = split
        while cursor < end and text[cursor].isspace():
            cursor += 1
    if cursor < end:
        chunks.append((cursor, end))
    return chunks


def _slug(value: str) -> str:
    return _NON_ID_RE.sub("_", value.strip().lower()).strip("_")[:80]
