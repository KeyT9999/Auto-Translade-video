"""Automatic repair for blocking translation issues."""

from __future__ import annotations

import json
import re

from src.utils import setup_logging

logger = setup_logging("translation_repair")


def _resolve_segment_text(segment: dict) -> str:
    for field_name in ("final_dub_vi", "dub_vi", "subtitle_vi", "text_vi", "literal_vi"):
        value = segment.get(field_name)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def build_repair_prompt(
    video_context: dict,
    glossary: dict,
    character_bible: dict,
    bad_segments: list[dict],
    issues: list[dict],
) -> str:
    repair_input = []
    for segment in bad_segments:
        seg_issues = [issue for issue in issues if issue.get("id") == segment.get("id")]
        issue_desc = "; ".join(
            f"{issue.get('type')}: {issue.get('message')}" for issue in seg_issues
        )
        repair_input.append(
            {
                "id": segment["id"],
                "source_text": segment.get("text", ""),
                "current_vi": _resolve_segment_text(segment),
                "duration": segment.get("duration", 0.0),
                "issues_to_fix": issue_desc,
            }
        )

    return f"""Ban la bien dich vien long tieng video chuyen nghiep.

Hay sua cac doan dich tieng Viet bi loi duoi day.
Yeu cau:
- Sua dung cac loi validator da neu.
- Khong de sot ky tu Trung/Nhat/Han.
- Cau phai tu nhien, gon, va giu dung nghia.
- Neu co glossary thi uu tien dung dung term.
- Khong doi id, source_text, hay duration.

STRICT OUTPUT:
Tra ve duy nhat 1 JSON object:
{{
  "repaired_segments": [
    {{
      "id": 1,
      "literal_vi": "...",
      "dub_vi": "...",
      "speaker": "NARRATOR",
      "speaker_gender": "neutral"
    }}
  ]
}}

VIDEO_CONTEXT:
{json.dumps(video_context, ensure_ascii=False, indent=2)}

GLOSSARY:
{json.dumps(glossary, ensure_ascii=False, indent=2)}

CHARACTER_BIBLE:
{json.dumps(character_bible, ensure_ascii=False, indent=2)}

SEGMENTS_TO_REPAIR:
{json.dumps(repair_input, ensure_ascii=False, indent=2)}
"""


def repair_translation(
    segments: list[dict],
    issues: list[dict],
    video_context: dict,
    glossary: dict,
    character_bible: dict,
    output_path: str | None = None,
) -> list[dict]:
    """Repair segments that still have blocking, repairable issues."""
    bad_ids = {
        issue["id"]
        for issue in issues
        if issue.get("id", 0) > 0 and issue.get("severity") == "error"
    }
    if not bad_ids:
        logger.info("No blocking issues passed into repair. Skipping repair stage.")
        return segments

    bad_segments = [segment for segment in segments if segment.get("id") in bad_ids]
    logger.info("Repairing %s segment(s) with blocking issues.", len(bad_segments))

    prompt = build_repair_prompt(video_context, glossary, character_bible, bad_segments, issues)

    from src.ai import ai_router

    try:
        response = ai_router.repair(prompt)
        repaired_segments = response.get("repaired_segments") if isinstance(response, dict) else None
    except Exception as exc:
        logger.error("Router repair failed: %s", exc)
        repaired_segments = None

    if not repaired_segments:
        logger.error("AI repair returned no usable segment payload.")
        if output_path:
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "repaired_count": 0,
                        "status": "failed",
                        "details": "AI repair returned no usable segment payload.",
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
        return segments

    repaired_map = {
        item["id"]: item
        for item in repaired_segments
        if isinstance(item, dict) and item.get("id") is not None
    }
    updated_segments: list[dict] = []
    repair_log: list[dict] = []

    for segment in segments:
        seg_id = segment.get("id")
        repaired = repaired_map.get(seg_id)
        if not repaired:
            updated_segments.append(segment)
            continue

        repaired_text = (
            repaired.get("final_dub_vi")
            or repaired.get("dub_vi")
            or repaired.get("subtitle_vi")
            or repaired.get("text_vi")
            or repaired.get("literal_vi")
            or _resolve_segment_text(segment)
        )
        cleaned_text = re.sub(r"[^\w\s\d,.\-!?]", "", repaired_text).strip()
        if not cleaned_text:
            repaired_text = "Ha."

        logger.info(
            "  Repaired Segment %s: '%s' -> '%s'",
            seg_id,
            _resolve_segment_text(segment),
            repaired_text,
        )
        repair_log.append(
            {
                "id": seg_id,
                "original": _resolve_segment_text(segment),
                "repaired": repaired_text,
            }
        )

        updated_segments.append(
            {
                **segment,
                "literal_vi": repaired.get("literal_vi", segment.get("literal_vi", repaired_text)),
                "text_vi": repaired_text,
                "subtitle_vi": repaired_text,
                "dub_vi": repaired_text,
                "final_dub_vi": repaired_text,
                "speaker": repaired.get("speaker", segment.get("speaker", "NARRATOR")),
                "speaker_gender": repaired.get(
                    "speaker_gender",
                    segment.get("speaker_gender", "neutral"),
                ),
                "risk_flags": list(segment.get("risk_flags", [])) + ["REPAIRED"],
            }
        )

    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "repaired_count": len(repair_log),
                        "status": "success",
                        "details": repair_log,
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
            logger.info("Saved translation repair report to %s", output_path)
        except Exception as exc:
            logger.error("Failed to save translation repair report: %s", exc)

    return updated_segments
