"""Translation Validator — Validates translated segments for quality, CJK leak, awkward phrasing, and duration issues."""
import json
import os
import re
from src.utils import setup_logging

logger = setup_logging("translation_validator")

CJK_RE = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf]')

# Common awkward phrases to flag
AWKWARD_PHRASES = {
    r"đâu cũng có thể ngồi": "Dịch ngượng vị trí, nên sửa thành 'chỗ này cũng ngồi được' hoặc 'ngồi đâu cũng được'",
    r"đâu nhìn rõ": "Dịch ngượng vị trí, nên sửa thành 'nhìn rõ hơn ở đây'",
    r"đâu là trong nhà": "Dịch ngượng vị trí, nên sửa thành 'đây là khu trong nhà'",
    r"cạnh này": "Có thể dùng sai ngữ cảnh chỉ vị trí bên cạnh",
    r"ngồi đâu": "Có thể dịch ngượng của 'ở đây ngồi được'",
    r"thế nào nhìn": "Có thể dịch ngượng của 'nhìn thế nào'"
}


def validate_translation(segments: list[dict], output_path: str = None, mode: str = "dub_audio") -> dict:
    """Validate list of translated segments and save a quality report."""
    issues = []
    total_segments = len(segments)
    
    # Track speakers to check if all are neutral in a multi-speaker context
    speakers = set()
    for s in segments:
        sp = s.get("speaker")
        if sp:
            speakers.add(sp)

    # If multiple segments exist but only one speaker "NARRATOR" with gender "neutral" is found, check if that's normal
    all_neutral = True
    for s in segments:
        if s.get("speaker_gender") != "neutral":
            all_neutral = False
            break

    for s in segments:
        seg_id = s.get("id")
        text_orig = s.get("text", "")
        
        # Resolve target text field for validation in priority order
        target_text = ""
        for field_name in ["subtitle_vi", "text_vi", "dub_vi", "literal_vi"]:
            if field_name in s and s[field_name] is not None:
                target_text = str(s[field_name])
                break
        if not target_text:
            target_text = str(s.get("text_vi", s.get("dub_vi", s.get("literal_vi", ""))))

        literal_vi = s.get("literal_vi", s.get("text_vi", ""))
        duration = s.get("duration", 0.0)

        # 1. Check CJK Leak
        for field in ["subtitle_vi", "text_vi", "dub_vi", "literal_vi"]:
            val = s.get(field)
            if val and CJK_RE.search(str(val)):
                issues.append({
                    "id": seg_id,
                    "field": field,
                    "severity": "error",
                    "type": "SOURCE_LANGUAGE_LEAK",
                    "message": f"Vietnamese text in '{field}' still contains CJK (Chinese/Japanese/Korean) characters",
                    "text": val
                })

        # 2. Check Empty / Null text
        if not target_text or not target_text.strip():
            issues.append({
                "id": seg_id,
                "field": "text_vi",
                "severity": "error",
                "type": "EMPTY_TEXT",
                "message": "Vietnamese text is empty",
                "text": target_text
            })

        # 3. Check Awkward phrasing
        if target_text:
            dub_lower = target_text.lower()
            for pattern, reason in AWKWARD_PHRASES.items():
                if re.search(pattern, dub_lower):
                    issues.append({
                        "id": seg_id,
                        "field": "text_vi",
                        "severity": "warning",
                        "type": "AWKWARD_PHRASING",
                        "message": reason,
                        "text": target_text
                    })

        # 4. Check Speech rate (chars/sec) - skip if subtitle_only
        if mode != "subtitle_only" and target_text and duration > 0:
            char_rate = len(target_text) / duration
            if char_rate > 15.0:
                issues.append({
                    "id": seg_id,
                    "field": "text_vi",
                    "severity": "warning",
                    "type": "TIMING_OVERFLOW",
                    "message": f"Dialogue rate is too high ({char_rate:.1f} chars/sec, duration {duration:.2f}s). Might not fit in timeline.",
                    "text": target_text
                })

        # 5. Check if untranslated (source text identical to translation)
        if target_text and text_orig:
            if target_text.strip().lower() == str(text_orig).strip().lower() and re.search(r'[a-zA-Z\u4e00-\u9fff\u3040-\u30ff]', str(text_orig)):
                issues.append({
                    "id": seg_id,
                    "field": "text_vi",
                    "severity": "error",
                    "type": "UNTRANSLATED_TEXT",
                    "message": "Translation is identical to the original text",
                    "text": target_text
                })

    # 6. Check if multi-speaker but all are neutral
    if len(speakers) > 1 and all_neutral:
        issues.append({
            "id": 0,
            "field": "speaker_gender",
            "severity": "warning",
            "type": "SPEAKER_NEUTRALITY",
            "message": "Multiple speakers identified but all speaker genders are neutral. Voice mapping might be monotonous.",
            "text": ""
        })

    bad_ids = {iss["id"] for iss in issues if iss["severity"] == "error" and iss["id"] > 0}
    valid_segments = total_segments - len(bad_ids)

    report = {
        "total_segments": total_segments,
        "valid_segments": valid_segments,
        "bad_segments": len(bad_ids),
        "issues": issues
    }

    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved translation quality report to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save translation quality report: {e}")

    return report
