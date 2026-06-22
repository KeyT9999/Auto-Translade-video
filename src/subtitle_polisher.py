"""Lightweight subtitle-only polish pass for Vietnamese readability."""

from __future__ import annotations

import re
import unicodedata

from src.glossary_enforcer import normalize_source_text
from src.utils import setup_logging

logger = setup_logging("subtitle_polisher")

TRANSLATION_FIELDS = (
    "literal_vi",
    "text_vi",
    "subtitle_vi",
    "dub_vi",
    "final_dub_vi",
)

RAW_TARGET_TEXT_OVERRIDES = {
    "Còn có điểm tâm nữa": "Còn có đồ ăn nhẹ nữa",
    "Mình đã đặt ba cái đồng hồ báo thức đấy": "Mình đặt tận ba cái báo thức đấy",
    "Quả nhiên đồ rẻ không có tốt": "Đúng là của rẻ khó ngon mà",
    "Hôm nay không viết đánh giá kém nữa": "Hôm nay khỏi viết đánh giá chê nữa",
    "Xong rồi, cái gì cũng muốn hết.": "Toang rồi, cái gì cũng muốn mua",
    "Xong rồi, cái gì cũng muốn hết": "Toang rồi, cái gì cũng muốn mua",
    "Chính là cái thuyền đó": "Chính là chiếc thuyền đó",
}


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.replace("đ", "d").replace("Đ", "D").casefold()


TARGET_TEXT_OVERRIDES = {
    _fold_text(source_text): target_text
    for source_text, target_text in RAW_TARGET_TEXT_OVERRIDES.items()
}


def _preferred_pronoun(character_bible: dict | None, field: str, fallback: str) -> str:
    if not isinstance(character_bible, dict):
        return fallback
    characters = character_bible.get("characters", [])
    if not isinstance(characters, list) or not characters:
        return fallback

    values = []
    for character in characters:
        if not isinstance(character, dict):
            continue
        value = str(character.get(field) or "").strip()
        if value:
            values.append(value)
    if not values:
        return fallback
    if len(set(values)) == 1:
        return values[0]
    return fallback


def _replace_standalone_word(text: str, old: str, new: str) -> str:
    if not old or old == new:
        return text
    return re.sub(
        rf"(?<![\wÀ-ỹ]){re.escape(old)}(?![\wÀ-ỹ])",
        new,
        text,
        flags=re.IGNORECASE,
    )


def _apply_source_specific_override(
    source_text: str,
    current_text: str,
    self_pronoun: str,
) -> str:
    normalized_source = normalize_source_text(source_text)
    if "飞天画舻" in normalized_source and "鸣笛" in normalized_source:
        return "Thuyền bay đã hú còi rồi"
    if "凌晨三点" in normalized_source and "顿波波间" in normalized_source:
        return f"3 giờ sáng {self_pronoun} đã dậy săn vé"
    return current_text


def _apply_target_override(current_text: str) -> str:
    return TARGET_TEXT_OVERRIDES.get(_fold_text(current_text), current_text)


def polish_subtitle_segments(
    segments: list[dict],
    character_bible: dict | None = None,
) -> list[dict]:
    if not segments:
        return segments

    preferred_self = _preferred_pronoun(character_bible, "vi_pronoun_self", "mình")
    preferred_other = _preferred_pronoun(character_bible, "vi_pronoun_other", "bạn")
    alternate_other = "cậu" if preferred_other == "bạn" else "bạn" if preferred_other == "cậu" else ""

    updated_segments: list[dict] = []
    changed_count = 0

    for segment in segments:
        updated_segment = dict(segment)
        segment_changed = False
        source_text = str(segment.get("text", ""))

        for field in TRANSLATION_FIELDS:
            current = updated_segment.get(field)
            if not current:
                continue

            rewritten = str(current)
            rewritten = _apply_source_specific_override(source_text, rewritten, preferred_self)
            rewritten = _apply_target_override(rewritten)
            if alternate_other:
                rewritten = _replace_standalone_word(rewritten, alternate_other, preferred_other)

            rewritten = re.sub(r"\s+", " ", rewritten).strip()
            if rewritten and rewritten != current:
                updated_segment[field] = rewritten
                segment_changed = True

        if segment_changed:
            changed_count += 1
            updated_segment["subtitle_polished"] = True
            updated_segment["risk_flags"] = list(updated_segment.get("risk_flags", [])) + [
                "SUBTITLE_POLISHED"
            ]

        updated_segments.append(updated_segment)

    if changed_count:
        logger.info("Subtitle polish updated %s segment(s).", changed_count)

    return updated_segments
