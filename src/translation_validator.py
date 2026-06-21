"""Translation quality validator with zh-CN aware warning vs blocking rules."""

from __future__ import annotations

import json
import re
import unicodedata

import config
from src.glossary_enforcer import detect_glossary_conflicts
from src.subtitle_group_rewriter import detect_fragmented_subtitle_pairs
from src.utils import setup_logging

logger = setup_logging("translation_validator")

CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf]")
LATIN_OR_CJK_RE = re.compile(r"[a-zA-Z\u4e00-\u9fff\u3040-\u30ff]")

AWKWARD_PATTERNS = {
    "dau cung co the ngoi": "Likely mirrored Chinese word order; rewrite into natural Vietnamese.",
    "dau nhin ro": "Likely mirrored Chinese word order; rewrite into natural Vietnamese.",
    "dau la trong nha": "Likely mirrored Chinese word order; rewrite into natural Vietnamese.",
    "canh nay": "This phrase sounds unnatural in conversational Vietnamese here.",
    "ngoi dau": "This phrase sounds unnatural in conversational Vietnamese here.",
    "the nao nhin": "This phrase sounds unnatural in conversational Vietnamese here.",
    "chu bao": "Possible untranslated Chinese-style phrasing.",
    "ai dong": "Possible untranslated Chinese-style phrasing.",
}

META_HALLUCINATION_PATTERNS = (
    "ban dich",
    "giai thich",
    "ghi chu",
    "theo ngu canh",
    "toi nghi",
    "translation note",
    "context note",
    "subtitle note",
)

WARNING_ONLY_ISSUE_TYPES = {
    "AWKWARD_TRANSLATION",
    "FRAGMENTED_SUBTITLE",
    "GLOSSARY_MISMATCH",
    "LENGTH_RATIO_WARNING",
    "READABILITY_WARNING",
    "SPEAKER_NEUTRALITY",
    "TIMING_OVERFLOW",
}

REPAIRABLE_ISSUE_TYPES = {
    "BANNED_WRONG_TERM",
    "EMPTY_TEXT",
    "SOURCE_LANGUAGE_LEAK",
    "TIMING_OVERFLOW",
    "TRUE_HALLUCINATION",
    "UNTRANSLATED_TEXT",
}


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.replace("đ", "d").replace("Đ", "D").casefold()


def _compact_len(value: str) -> int:
    return len(re.sub(r"\s+", "", value or ""))


def _resolve_target_text(segment: dict, mode: str) -> str:
    if mode == "subtitle_only":
        fields = ("subtitle_vi", "text_vi", "dub_vi", "final_dub_vi", "literal_vi")
    else:
        fields = ("final_dub_vi", "dub_vi", "text_vi", "subtitle_vi", "literal_vi")
    for field_name in fields:
        value = segment.get(field_name)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _make_issue(
    segment_id: int,
    field: str,
    issue_type: str,
    message: str,
    text: str = "",
    severity: str = "warning",
    blocking: bool | None = None,
    repairable: bool | None = None,
    recommended_action: str | None = None,
    **extra,
) -> dict:
    if blocking is None:
        blocking = severity == "error" and issue_type not in WARNING_ONLY_ISSUE_TYPES
    if repairable is None:
        repairable = issue_type in REPAIRABLE_ISSUE_TYPES
    if recommended_action is None:
        if blocking and repairable:
            recommended_action = "repair"
        elif issue_type in {"AWKWARD_TRANSLATION", "FRAGMENTED_SUBTITLE", "GLOSSARY_MISMATCH"}:
            recommended_action = "quality_rewrite"
        else:
            recommended_action = "warn"

    issue = {
        "id": segment_id,
        "field": field,
        "severity": severity,
        "type": issue_type,
        "message": message,
        "text": text,
        "blocking": blocking,
        "repairable": repairable,
        "recommended_action": recommended_action,
    }
    issue.update(extra)
    return issue


def is_blocking_issue(issue: dict) -> bool:
    if "blocking" in issue:
        return bool(issue["blocking"])
    return issue.get("severity") == "error" and issue.get("type") not in WARNING_ONLY_ISSUE_TYPES


def filter_repairable_issues(issues: list[dict]) -> list[dict]:
    return [issue for issue in issues if is_blocking_issue(issue) and issue.get("repairable", False)]


def has_blocking_errors(report_or_issues: dict | list[dict]) -> bool:
    issues = report_or_issues.get("issues", []) if isinstance(report_or_issues, dict) else report_or_issues
    return any(is_blocking_issue(issue) for issue in issues)


def _is_zh_source(source_text: str, source_language: str | None) -> bool:
    if source_language and str(source_language).lower().startswith("zh"):
        return True
    return bool(CJK_RE.search(source_text or ""))


def _looks_like_true_hallucination(
    source_text: str,
    target_text: str,
    source_language: str | None,
) -> bool:
    if not getattr(config, "VALIDATOR_HALLUCINATION_ENABLED", True):
        return False

    source_len = max(_compact_len(source_text), 1)
    target_len = _compact_len(target_text)
    ratio = target_len / source_len
    target_fold = _fold_text(target_text)
    is_zh_source = _is_zh_source(source_text, source_language)

    if any(pattern in target_fold for pattern in META_HALLUCINATION_PATTERNS):
        return True

    clause_count = sum(target_text.count(mark) for mark in (",", ";", ".", "!", "?"))

    if is_zh_source:
        hard_ratio = getattr(config, "VALIDATOR_ZH_VI_LENGTH_RATIO_ERROR_THRESHOLD", 8.0)
        return ratio >= hard_ratio and (target_len >= 80 or clause_count >= 3 or source_len <= 6)

    hard_ratio = max(getattr(config, "VALIDATOR_HALLUCINATION_SOURCE_CHAR_RATIO", 2.5) * 1.75, 4.0)
    return ratio >= hard_ratio and (target_len >= 80 or clause_count >= 3)


def validate_translation(
    segments: list[dict],
    output_path: str | None = None,
    mode: str = "dub_audio",
    source_language: str | None = None,
    glossary: dict | None = None,
) -> dict:
    issues: list[dict] = []
    total_segments = len(segments)
    speakers = {segment.get("speaker") for segment in segments if segment.get("speaker")}
    all_neutral = all(
        str(segment.get("speaker_gender", "neutral")).strip().lower() == "neutral"
        for segment in segments
    )

    for segment in segments:
        seg_id = int(segment.get("id", 0) or 0)
        source_text = str(segment.get("text", ""))
        target_text = _resolve_target_text(segment, mode)
        duration = float(segment.get("duration", 0.0) or 0.0)
        target_fold = _fold_text(target_text)

        for field_name in ("subtitle_vi", "text_vi", "dub_vi", "final_dub_vi", "literal_vi"):
            value = segment.get(field_name)
            if value and CJK_RE.search(str(value)):
                issues.append(
                    _make_issue(
                        seg_id,
                        field_name,
                        "SOURCE_LANGUAGE_LEAK",
                        f"Translated field '{field_name}' still contains CJK characters.",
                        text=str(value),
                        severity="error",
                    )
                )

        if not target_text.strip():
            issues.append(
                _make_issue(
                    seg_id,
                    "text_vi",
                    "EMPTY_TEXT",
                    "Vietnamese text is empty.",
                    severity="error",
                )
            )
            continue

        for pattern, message in AWKWARD_PATTERNS.items():
            if pattern in target_fold:
                issues.append(
                    _make_issue(
                        seg_id,
                        "text_vi",
                        "AWKWARD_TRANSLATION",
                        message,
                        text=target_text,
                        severity="warning",
                    )
                )

        source_len = _compact_len(source_text)
        target_len = _compact_len(target_text)
        if source_len > 3 and target_len > 0:
            ratio = target_len / source_len
            is_zh_source = _is_zh_source(source_text, source_language)

            if _looks_like_true_hallucination(source_text, target_text, source_language):
                issues.append(
                    _make_issue(
                        seg_id,
                        "text_vi",
                        "TRUE_HALLUCINATION",
                        f"Target text appears substantially hallucinated ({target_len} vs {source_len} chars).",
                        text=target_text,
                        severity="error",
                    )
                )
            elif is_zh_source:
                warning_threshold = getattr(config, "VALIDATOR_ZH_VI_LENGTH_RATIO_WARNING_THRESHOLD", 5.0)
                error_threshold = getattr(config, "VALIDATOR_ZH_VI_LENGTH_RATIO_ERROR_THRESHOLD", 8.0)
                as_error = getattr(config, "VALIDATOR_ZH_VI_LENGTH_RATIO_AS_ERROR", False)
                if ratio >= warning_threshold:
                    severity = "error" if as_error and ratio >= error_threshold else "warning"
                    issue_type = "TRUE_HALLUCINATION" if severity == "error" else "LENGTH_RATIO_WARNING"
                    issues.append(
                        _make_issue(
                            seg_id,
                            "text_vi",
                            issue_type,
                            f"zh-CN source expanded to {ratio:.2f}x target length; review for brevity.",
                            text=target_text,
                            severity=severity,
                            blocking=severity == "error",
                            repairable=severity == "error",
                        )
                    )
            else:
                threshold = getattr(config, "VALIDATOR_HALLUCINATION_SOURCE_CHAR_RATIO", 2.5)
                if ratio >= threshold:
                    issues.append(
                        _make_issue(
                            seg_id,
                            "text_vi",
                            "LENGTH_RATIO_WARNING",
                            f"Target text is {ratio:.2f}x longer than source text; review for brevity.",
                            text=target_text,
                            severity="warning",
                        )
                    )

        if duration > 0:
            char_rate = len(target_text) / duration
            subtitle_soft_limit = getattr(config, "VALIDATOR_SUBTITLE_MAX_CHARS_PER_SECOND", 22.0)
            subtitle_hard_limit = getattr(config, "VALIDATOR_SUBTITLE_HARD_MAX_CHARS_PER_SECOND", 32.0)
            if char_rate > subtitle_soft_limit:
                timing_message = (
                    f"Dialogue rate is high ({char_rate:.1f} chars/sec, duration {duration:.2f}s)."
                )
                if mode == "subtitle_only":
                    issues.append(
                        _make_issue(
                            seg_id,
                            "text_vi",
                            "TIMING_OVERFLOW",
                            timing_message,
                            text=target_text,
                            severity="warning",
                            blocking=False,
                            repairable=False,
                        )
                    )
                else:
                    severity = "error" if char_rate >= subtitle_hard_limit else "warning"
                    issues.append(
                        _make_issue(
                            seg_id,
                            "text_vi",
                            "TIMING_OVERFLOW",
                            timing_message,
                            text=target_text,
                            severity=severity,
                            blocking=severity == "error",
                            repairable=severity == "error",
                        )
                    )

        if mode == "subtitle_only" and len(target_text) > 42:
            issues.append(
                _make_issue(
                    seg_id,
                    "subtitle_vi",
                    "READABILITY_WARNING",
                    "Subtitle line is long and may be harder to read comfortably.",
                    text=target_text,
                    severity="warning",
                    blocking=False,
                    repairable=False,
                )
            )

        if source_text and target_text:
            if _fold_text(target_text) == _fold_text(source_text) and LATIN_OR_CJK_RE.search(source_text):
                issues.append(
                    _make_issue(
                        seg_id,
                        "text_vi",
                        "UNTRANSLATED_TEXT",
                        "Translation is identical to the source text.",
                        text=target_text,
                        severity="error",
                    )
                )

        for conflict in detect_glossary_conflicts(source_text, target_text, glossary):
            issue_type = conflict["type"]
            if issue_type == "BANNED_WRONG_TERM":
                issues.append(
                    _make_issue(
                        seg_id,
                        "text_vi",
                        issue_type,
                        f"Detected banned term '{conflict['matched_target']}' for source term '{conflict['source_term']}'. Expected '{conflict['expected_target']}'.",
                        text=target_text,
                        severity="error",
                        source_term=conflict["source_term"],
                        expected_target=conflict["expected_target"],
                    )
                )
            else:
                issues.append(
                    _make_issue(
                        seg_id,
                        "text_vi",
                        issue_type,
                        f"Source term '{conflict['source_term']}' should map to '{conflict['expected_target']}'.",
                        text=target_text,
                        severity="warning",
                        blocking=False,
                        repairable=False,
                        source_term=conflict["source_term"],
                        expected_target=conflict["expected_target"],
                    )
                )

    for fragment_issue in detect_fragmented_subtitle_pairs(segments):
        issues.append(
            _make_issue(
                int(fragment_issue["first_id"] or 0),
                "subtitle_vi",
                "FRAGMENTED_SUBTITLE",
                fragment_issue["message"],
                severity="warning",
                blocking=False,
                repairable=False,
                recommended_action="quality_rewrite",
                linked_segment_id=fragment_issue["second_id"],
                suggested_first=fragment_issue["suggested_first"],
                suggested_second=fragment_issue["suggested_second"],
            )
        )

    if len(speakers) > 1 and all_neutral:
        issues.append(
            _make_issue(
                0,
                "speaker_gender",
                "SPEAKER_NEUTRALITY",
                "Multiple speakers are present but all mapped genders are neutral.",
                severity="warning",
                blocking=False,
                repairable=False,
            )
        )

    blocking_ids = {issue["id"] for issue in issues if issue["id"] > 0 and is_blocking_issue(issue)}
    warning_ids = {
        issue["id"]
        for issue in issues
        if issue["id"] > 0 and not is_blocking_issue(issue)
    }
    repairable_ids = {
        issue["id"]
        for issue in issues
        if issue["id"] > 0 and issue.get("repairable", False)
    }
    quality_rewrite_ids = {
        issue["id"]
        for issue in issues
        if issue["id"] > 0 and issue.get("recommended_action") == "quality_rewrite"
    }

    report = {
        "total_segments": total_segments,
        "valid_segments": total_segments - len(blocking_ids),
        "bad_segments": len(blocking_ids),
        "blocking_segments": len(blocking_ids),
        "warning_segments": len(warning_ids),
        "repairable_segments": len(repairable_ids),
        "quality_rewrite_segments": len(quality_rewrite_ids),
        "issues": issues,
    }

    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
            logger.info("Saved translation quality report to %s", output_path)
        except Exception as exc:
            logger.error("Failed to save translation quality report: %s", exc)

    return report
