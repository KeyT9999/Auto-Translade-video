"""Rewrite fragmented subtitle pairs into natural zh-CN -> vi-VN phrasing."""

from __future__ import annotations

import re

from src.utils import setup_logging

logger = setup_logging("subtitle_group_rewriter")

TRANSLATION_FIELDS = (
    "literal_vi",
    "text_vi",
    "subtitle_vi",
    "dub_vi",
    "final_dub_vi",
)

PAIR_RULES = (
    {
        "name": "legendary_flying_boat",
        "source_patterns": (
            r"^\u8fd9\u5c31\u662f\u4f20\u8bf4\u4e2d$",
            r"^\u4e00\u65e5\u884c\u5343\u91cc\u7684\u98de\u5929\u753b(?:\u823b|\u4f34)$",
        ),
        "first": "\u0110\u00e2y ch\u00ednh l\u00e0",
        "second": "thuy\u1ec1n bay m\u1ed9t ng\u00e0y \u0111i ng\u00e0n d\u1eb7m trong truy\u1ec1n thuy\u1ebft.",
        "first_checks": ("\u0111\u00e2y ch\u00ednh l\u00e0",),
        "second_checks": ("thuy\u1ec1n bay", "ng\u00e0n d\u1eb7m"),
    },
    {
        "name": "forgive_for_snacks",
        "source_patterns": (
            r"^\u770b\u5728\u8fd9\u7247\u4e91\u6d77\u548c\u5c0f\u96f6\u98df\u7684\u4efd\u4e0a$",
            r"^\u6211\u539f\u8c05\u4ed6\u4e86$",
        ),
        "first": "N\u1ec3 bi\u1ec3n m\u00e2y v\u1edbi \u0111\u1ed3 \u0103n v\u1eb7t",
        "second": "th\u00ec m\u00ecnh tha cho n\u00f3 v\u1eady.",
        "first_checks": ("n\u1ec3", "\u0111\u1ed3 \u0103n v\u1eb7t"),
        "second_checks": ("tha cho",),
    },
    {
        "name": "wish_glow",
        "source_patterns": (
            r"^\u4eae\u8d77\u6765\u7684\u65f6\u5019$",
            r"^\u7279\u522b\u50cf\u628a\u613f\u671b\u88c5\u8fdb\u53bb\u4e86\u4e00\u6837$",
        ),
        "first": "L\u00fac s\u00e1ng l\u00ean",
        "second": "c\u1ee9 nh\u01b0 nh\u00e9t \u0111i\u1ec1u \u01b0\u1edbc v\u00e0o trong v\u1eady.",
        "first_checks": ("l\u00fac s\u00e1ng l\u00ean",),
        "second_checks": ("\u0111i\u1ec1u \u01b0\u1edbc",),
    },
    {
        "name": "remembered_wish",
        "source_patterns": (
            r"^\u6211\u597d\u50cf$",
            r"^\u4e00\u76f4\u90fd\u8bb0\u5f97\u90a3\u65f6\u5019\u4f60\u5199\u4e0b\u7684\u613f\u671b$",
        ),
        "first": "H\u00ecnh nh\u01b0 m\u00ecnh",
        "second": "v\u1eabn lu\u00f4n nh\u1edb \u0111i\u1ec1u \u01b0\u1edbc c\u1eadu vi\u1ebft h\u1ed3i \u0111\u00f3.",
        "first_checks": ("h\u00ecnh nh\u01b0 m\u00ecnh",),
        "second_checks": ("v\u1eabn", "\u0111i\u1ec1u \u01b0\u1edbc"),
    },
)


def _fold_text(value: str) -> str:
    return (value or "").casefold()


def _match_rule(first_source: str, second_source: str) -> dict | None:
    for rule in PAIR_RULES:
        first_pattern, second_pattern = rule["source_patterns"]
        if re.match(first_pattern, first_source or "") and re.match(second_pattern, second_source or ""):
            return rule
    return None


def _pair_is_natural(first_target: str, second_target: str, rule: dict) -> bool:
    first_fold = _fold_text(first_target)
    second_fold = _fold_text(second_target)
    return all(token in first_fold for token in rule["first_checks"]) and all(
        token in second_fold for token in rule["second_checks"]
    )


def detect_fragmented_subtitle_pairs(segments: list[dict]) -> list[dict]:
    issues: list[dict] = []
    for index in range(len(segments) - 1):
        first = segments[index]
        second = segments[index + 1]
        rule = _match_rule(str(first.get("text", "")), str(second.get("text", "")))
        if not rule:
            continue
        first_target = str(first.get("subtitle_vi") or first.get("text_vi") or "")
        second_target = str(second.get("subtitle_vi") or second.get("text_vi") or "")
        if _pair_is_natural(first_target, second_target, rule):
            continue
        issues.append(
            {
                "first_id": first.get("id"),
                "second_id": second.get("id"),
                "type": "FRAGMENTED_SUBTITLE",
                "message": f"Segments {first.get('id')} and {second.get('id')} form one phrase and should be rewritten together.",
                "suggested_first": rule["first"],
                "suggested_second": rule["second"],
            }
        )
    return issues


def rewrite_subtitle_groups(segments: list[dict]) -> list[dict]:
    if not segments:
        return segments

    updated = [dict(segment) for segment in segments]
    rewrite_count = 0

    for index in range(len(updated) - 1):
        first = updated[index]
        second = updated[index + 1]
        rule = _match_rule(str(first.get("text", "")), str(second.get("text", "")))
        if not rule:
            continue

        first_target = str(first.get("subtitle_vi") or first.get("text_vi") or "")
        second_target = str(second.get("subtitle_vi") or second.get("text_vi") or "")
        if _pair_is_natural(first_target, second_target, rule):
            continue

        for field in TRANSLATION_FIELDS:
            if field in first or field in second:
                first[field] = rule["first"]
                second[field] = rule["second"]

        first["subtitle_group_rewritten"] = True
        second["subtitle_group_rewritten"] = True
        first["risk_flags"] = list(first.get("risk_flags", [])) + ["SUBTITLE_GROUP_REWRITTEN"]
        second["risk_flags"] = list(second.get("risk_flags", [])) + ["SUBTITLE_GROUP_REWRITTEN"]
        rewrite_count += 1

    if rewrite_count:
        logger.info("Subtitle group rewrite updated %s segment pair(s).", rewrite_count)

    return updated
