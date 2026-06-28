"""Timeline-aware rewrite that only shortens Vietnamese dubbing safely."""

from __future__ import annotations

import json
import re
import unicodedata

from src.utils import setup_logging

logger = setup_logging("timeline_rewriter")

TRANSLATION_FIELDS = ("dub_vi", "final_dub_vi", "text_vi", "subtitle_vi")
BANNED_EXPANSION_PATTERNS = (
    "mọi người",
    "các bạn",
    "thấy không",
    "đừng lo",
    "đừng lo lắng",
    "thật sự là",
    "thực sự là",
)
CLAUSE_SPLIT_RE = re.compile(r"[,.!?;:…]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf]")


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.replace("đ", "d").replace("Đ", "D").casefold()


def _count_clauses(text: str) -> int:
    chunks = [part.strip() for part in CLAUSE_SPLIT_RE.split(_normalize_spaces(text)) if part.strip()]
    return max(len(chunks), 1) if _normalize_spaces(text) else 0


def _base_dub_text(segment: dict) -> str:
    original = _normalize_spaces(str(segment.get("original_dub_vi", "")))
    if segment.get("timing_rewrite_applied") and original:
        return original
    for field in ("dub_vi", "final_dub_vi", "text_vi", "subtitle_vi", "literal_vi"):
        value = _normalize_spaces(str(segment.get(field, "")))
        if value:
            return value
    return ""


def _contains_banned_expansion(text: str) -> str | None:
    folded = _fold_text(text)
    return next((pattern for pattern in BANNED_EXPANSION_PATTERNS if pattern in folded), None)


def _validate_rewrite(original_text: str, rewritten_text: str) -> tuple[bool, str]:
    original = _normalize_spaces(original_text)
    rewritten = _normalize_spaces(rewritten_text)

    if not rewritten:
        return False, "empty rewrite"
    if CJK_RE.search(rewritten):
        return False, "contains CJK characters"
    if len(rewritten) > len(original):
        return False, "rewrite is longer than original"
    if _count_clauses(rewritten) > _count_clauses(original):
        return False, "rewrite adds more clauses than original"

    banned_pattern = _contains_banned_expansion(rewritten)
    if banned_pattern:
        return False, f"rewrite contains banned expansion pattern '{banned_pattern}'"

    return True, "accepted"


def build_rewrite_prompt(
    video_context: dict,
    character_bible: dict,
    segments_to_rewrite: list[dict],
) -> str:
    prompt_items = []
    for segment in segments_to_rewrite:
        base_dub = _base_dub_text(segment)
        char_rate = len(base_dub) / segment["duration"] if segment["duration"] > 0 else 0
        prompt_items.append(
            {
                "id": segment["id"],
                "source_text": segment["text"],
                "dub_vi": base_dub,
                "duration": segment["duration"],
                "char_rate_chars_per_sec": round(char_rate, 1),
            }
        )

    return f"""Bạn là chuyên gia chỉnh câu thoại lồng tiếng tiếng Việt để khớp thời lượng.

Nhiệm vụ:
- Chỉ RÚT GỌN câu dub_vi nếu cần để đọc vừa duration.
- Không được thêm ý mới.
- Không được thêm lời kêu gọi khán giả như "mọi người", "các bạn", "thấy không".
- Không được thêm các đuôi kéo dài kiểu "thật sự là như vậy đó", "đừng lo lắng nhé".
- Không được làm câu dài hơn bản gốc.
- Không được tăng số mệnh đề/câu so với bản gốc.
- Nếu không rút gọn an toàn được thì giữ nguyên bản gốc.
- Giữ nguyên xưng hô theo CHARACTER_BIBLE.
- Không để sót ký tự CJK.

STRICT OUTPUT FORMAT:
Trả về duy nhất 1 JSON object:
{{
  "rewritten_segments": [
    {{
      "id": 1,
      "final_dub_vi": "câu rút gọn an toàn"
    }}
  ]
}}

VIDEO_CONTEXT:
{json.dumps(video_context, ensure_ascii=False, indent=2)}

CHARACTER_BIBLE:
{json.dumps(character_bible, ensure_ascii=False, indent=2)}

SEGMENTS_TO_REWRITE:
{json.dumps(prompt_items, ensure_ascii=False, indent=2)}
"""


def rewrite_timeline(
    segments: list[dict],
    video_context: dict,
    character_bible: dict,
) -> list[dict]:
    """Safely shorten only the genuinely too-long segments."""
    if not segments:
        return segments

    prepared_segments = []
    to_rewrite = []

    for segment in segments:
        base_dub = _base_dub_text(segment)
        prepared = {**segment, "original_dub_vi": base_dub}
        prepared_segments.append(prepared)

        duration = float(segment.get("duration", 0.0) or 0.0)
        if not base_dub or duration <= 0:
            continue

        char_rate = len(base_dub) / duration
        if char_rate > 15.0:
            to_rewrite.append(prepared)

    if not to_rewrite:
        logger.info("No segments need timing adjustment.")
        return [
            {
                **segment,
                "timing_rewrite_applied": False,
                "original_dub_vi": segment.get("original_dub_vi", ""),
                **{field: segment.get("original_dub_vi", "") for field in TRANSLATION_FIELDS},
            }
            if segment.get("original_dub_vi")
            else {
                **segment,
                "timing_rewrite_applied": False,
                "original_dub_vi": _base_dub_text(segment),
                **{field: _base_dub_text(segment) for field in TRANSLATION_FIELDS},
            }
            for segment in prepared_segments
        ]

    logger.info("Found %s segments requiring timeline rewrite.", len(to_rewrite))

    # Process in batches to avoid API timeouts on long videos
    import config
    batch_size = getattr(config, "TIMELINE_REWRITE_BATCH_SIZE", 25)
    rewritten_results = []

    from src.ai import ai_router

    for idx in range(0, len(to_rewrite), batch_size):
        batch = to_rewrite[idx : idx + batch_size]
        logger.info(
            "  Processing timeline rewrite batch: segments %s to %s of %s...",
            idx + 1,
            min(idx + batch_size, len(to_rewrite)),
            len(to_rewrite),
        )
        prompt = build_rewrite_prompt(video_context, character_bible, batch)
        try:
            res_dict = ai_router.rewrite_timeline(prompt)
            batch_results = res_dict.get("rewritten_segments") if isinstance(res_dict, dict) else None
            if batch_results:
                rewritten_results.extend(batch_results)
        except Exception as exc:
            logger.error("Router timeline rewrite failed for batch starting at index %s: %s", idx, exc)

    if not rewritten_results:
        logger.warning("Timeline rewrite AI failed or returned empty results. Proceeding with original translations.")
        rewritten_results = []

    rewritten_map = {
        item["id"]: _normalize_spaces(str(item.get("final_dub_vi", "")))
        for item in rewritten_results
        if isinstance(item, dict) and item.get("id") is not None
    }

    updated_segments = []
    for segment in prepared_segments:
        seg_id = segment["id"]
        original_dub = segment.get("original_dub_vi", "")
        candidate = rewritten_map.get(seg_id, "")

        if candidate:
            accepted, reason = _validate_rewrite(original_dub, candidate)
            if accepted:
                logger.info("  Timeline rewritten segment %s: '%s' -> '%s'", seg_id, original_dub, candidate)
                updated_segments.append(
                    {
                        **segment,
                        "timing_rewrite_applied": True,
                        **{field: candidate for field in TRANSLATION_FIELDS},
                    }
                )
                continue

            logger.warning(
                "  Rejected timeline rewrite for segment %s (%s): '%s' -> '%s'",
                seg_id,
                reason,
                original_dub,
                candidate,
            )

        updated_segments.append(
            {
                **segment,
                "timing_rewrite_applied": False,
                **{field: original_dub for field in TRANSLATION_FIELDS},
            }
        )

    return updated_segments
