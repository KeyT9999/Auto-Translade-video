"""Glossary enforcement helpers for zh-CN -> vi-VN translations."""

from __future__ import annotations

import re
import unicodedata

from src.utils import setup_logging

logger = setup_logging("glossary_enforcer")

TRANSLATION_FIELDS = (
    "literal_vi",
    "text_vi",
    "subtitle_vi",
    "dub_vi",
    "final_dub_vi",
)

FLYING_BOAT_CANONICAL = "飞天画舻"
TICKET_HUNT_CANONICAL = "顿波波间"

FLYING_BOAT_VARIANT_RE = re.compile(r"飞天画(?:像|伴|舻|舫|船|舟)")
TICKET_HUNT_VARIANT_RE = re.compile(r"顿波波(?:间|間)")

SOURCE_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    FLYING_BOAT_CANONICAL: (
        FLYING_BOAT_CANONICAL,
        "飞天画像",
        "飞天画伴",
        "飞天画舫",
        "飞天画船",
        "飞天画舟",
    ),
    "\u4e91\u6d77\u6e21\u53e3": ("\u4e91\u6d77\u6e21\u53e3",),
    "\u6c5f\u5357": ("\u6c5f\u5357",),
    "\u9713\u88f3\u8282": ("\u9713\u88f3\u8282",),
    "\u957f\u660e\u9601": ("\u957f\u660e\u9601",),
    TICKET_HUNT_CANONICAL: (TICKET_HUNT_CANONICAL, "顿波波間"),
}

LOCKED_TARGETS: dict[str, str] = {
    FLYING_BOAT_CANONICAL: "thuyền bay",
    TICKET_HUNT_CANONICAL: "săn vé",
}

DEFAULT_FORCE_TARGETS: dict[str, str] = {
    FLYING_BOAT_CANONICAL: "thuy\u1ec1n bay",
    "\u4e91\u6d77\u6e21\u53e3": "b\u1ebfn m\u00e2y",
    "\u6c5f\u5357": "Giang Nam",
    "\u9713\u88f3\u8282": "L\u1ec5 h\u1ed9i Ngh\u00ea Th\u01b0\u1eddng",
    "\u957f\u660e\u9601": "Tr\u01b0\u1eddng Minh C\u00e1c",
    TICKET_HUNT_CANONICAL: "s\u0103n v\u00e9",
}

BANNED_TARGET_VARIANTS: dict[str, tuple[str, ...]] = {
    FLYING_BOAT_CANONICAL: (
        "tranh bay",
        "hoa ban bay",
        "bức họa phi thiên",
        "bạn vẽ phi thiên",
        "tranh phi thiên",
    ),
    "\u4e91\u6d77\u6e21\u53e3": (
        "v\u00e2n h\u1ea3i \u0111\u1ed9",
        "van hai do",
    ),
    TICKET_HUNT_CANONICAL: (
        "ph\u00f2ng livestream",
        "livestream",
        "Đốn Ba Ba Gian",
        "đốn ba ba gian",
    ),
}


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.replace("đ", "d").replace("Đ", "D").casefold()


def normalize_source_term(term: str) -> str:
    term = (term or "").strip()
    if FLYING_BOAT_VARIANT_RE.fullmatch(term):
        return FLYING_BOAT_CANONICAL
    if TICKET_HUNT_VARIANT_RE.fullmatch(term):
        return TICKET_HUNT_CANONICAL
    for canonical, aliases in SOURCE_TERM_ALIASES.items():
        if term == canonical or term in aliases:
            return canonical
    return term


def _preferred_target(raw_value: str) -> str:
    if not raw_value:
        return ""
    parts = [part.strip() for part in re.split(r"\s*/\s*", str(raw_value)) if part.strip()]
    return parts[0] if parts else str(raw_value).strip()


def sanitize_glossary(glossary: dict | None = None) -> dict:
    sanitized = dict(glossary) if isinstance(glossary, dict) else {}
    terms = sanitized.get("terms", {})
    if not isinstance(terms, dict):
        terms = {}

    normalized_terms: dict[str, str] = {}
    for source_term, target_term in terms.items():
        canonical = normalize_source_term(str(source_term))
        preferred = _preferred_target(str(target_term))
        if not canonical or not preferred:
            continue
        if canonical in LOCKED_TARGETS:
            normalized_terms[canonical] = LOCKED_TARGETS[canonical]
            continue
        normalized_terms.setdefault(canonical, preferred)

    for canonical, preferred in LOCKED_TARGETS.items():
        normalized_terms[canonical] = preferred

    sanitized["terms"] = normalized_terms
    return sanitized


def build_effective_glossary(glossary: dict | None = None) -> dict[str, str]:
    effective = dict(DEFAULT_FORCE_TARGETS)
    terms = sanitize_glossary(glossary).get("terms", {})
    for source_term, target_term in terms.items():
        canonical = normalize_source_term(str(source_term))
        preferred = LOCKED_TARGETS.get(canonical) or _preferred_target(str(target_term))
        if preferred:
            effective[canonical] = preferred
    return effective


def normalize_source_text(source_text: str) -> str:
    text = source_text or ""
    text = FLYING_BOAT_VARIANT_RE.sub(FLYING_BOAT_CANONICAL, text)
    text = TICKET_HUNT_VARIANT_RE.sub(TICKET_HUNT_CANONICAL, text)
    for canonical, aliases in SOURCE_TERM_ALIASES.items():
        for alias in aliases:
            if alias != canonical:
                text = text.replace(alias, canonical)
    return text


def get_source_terms_in_text(source_text: str, glossary: dict | None = None) -> list[str]:
    normalized_source = normalize_source_text(source_text or "")
    effective = build_effective_glossary(glossary)
    found: list[str] = []
    for canonical in effective:
        if canonical in normalized_source:
            found.append(canonical)
    return found


def detect_glossary_conflicts(
    source_text: str,
    target_text: str,
    glossary: dict | None = None,
) -> list[dict]:
    conflicts: list[dict] = []
    target_fold = _fold_text(target_text or "")
    effective = build_effective_glossary(glossary)

    for canonical in get_source_terms_in_text(source_text, glossary):
        preferred = effective.get(canonical, "")
        preferred_fold = _fold_text(preferred)
        banned_match = next(
            (
                variant
                for variant in BANNED_TARGET_VARIANTS.get(canonical, ())
                if _fold_text(variant) in target_fold
            ),
            None,
        )
        if banned_match:
            conflicts.append(
                {
                    "type": "BANNED_WRONG_TERM",
                    "source_term": canonical,
                    "expected_target": preferred,
                    "matched_target": banned_match,
                }
            )
            continue
        if preferred and preferred_fold and preferred_fold not in target_fold:
            conflicts.append(
                {
                    "type": "GLOSSARY_MISMATCH",
                    "source_term": canonical,
                    "expected_target": preferred,
                    "matched_target": "",
                }
            )

    return conflicts


def apply_glossary_to_text(
    source_text: str,
    target_text: str,
    glossary: dict | None = None,
) -> tuple[str, list[dict]]:
    updated_text = target_text or ""
    conflicts = detect_glossary_conflicts(source_text, updated_text, glossary)
    effective = build_effective_glossary(glossary)
    applied: list[dict] = []

    for conflict in conflicts:
        if conflict["type"] != "BANNED_WRONG_TERM":
            continue
        canonical = conflict["source_term"]
        preferred = effective.get(canonical, "")
        if not preferred:
            continue
        for variant in BANNED_TARGET_VARIANTS.get(canonical, ()):
            updated_text = re.sub(re.escape(variant), preferred, updated_text, flags=re.IGNORECASE)
        applied.append(conflict)

    return updated_text, applied


def apply_glossary_to_segments(
    segments: list[dict],
    glossary: dict | None = None,
) -> list[dict]:
    if not segments:
        return segments

    updated_segments: list[dict] = []
    changed_count = 0

    for segment in segments:
        source_text = str(segment.get("text", ""))
        updated_segment = dict(segment)
        segment_changes: list[dict] = []

        for field in TRANSLATION_FIELDS:
            current = updated_segment.get(field)
            if not current:
                continue
            rewritten, applied = apply_glossary_to_text(source_text, str(current), glossary)
            if applied and rewritten != current:
                updated_segment[field] = rewritten
                segment_changes.extend(applied)

        if segment_changes:
            changed_count += 1
            updated_segment["glossary_enforced"] = True
            updated_segment["risk_flags"] = list(updated_segment.get("risk_flags", [])) + [
                "GLOSSARY_ENFORCED"
            ]

        updated_segments.append(updated_segment)

    if changed_count:
        logger.info("Glossary enforcement updated %s segment(s).", changed_count)

    return updated_segments
