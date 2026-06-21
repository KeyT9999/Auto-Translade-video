"""Translation Repair — Automatically repairs translated segments that failed validation checks using Gemini/Groq."""
import json
import os
import re
import requests
import config
from src.utils import setup_logging

logger = setup_logging("translation_repair")


def build_repair_prompt(
    video_context: dict,
    glossary: dict,
    character_bible: dict,
    bad_segments: list[dict],
    issues: list[dict]
) -> str:
    # Build list of segments to fix along with their validation issues
    repaired_input = []
    for s in bad_segments:
        seg_issues = [iss for iss in issues if iss["id"] == s["id"]]
        issue_desc = "; ".join([f"{iss['type']}: {iss['message']}" for iss in seg_issues])
        repaired_input.append({
            "id": s["id"],
            "source_text": s["text"],
            "failed_dub_vi": s["dub_vi"],
            "duration": s["duration"],
            "issues_to_fix": issue_desc
        })

    prompt = f"""Bạn là biên dịch viên lồng tiếng video chuyên nghiệp. Một số phân đoạn trong bản dịch tiếng Việt trước đó đã bị đánh giá LỖI bởi hệ thống kiểm định tự động (Ví dụ: còn sót chữ Trung Quốc, dịch ngượng vị trí, hoặc câu quá dài).

Nhiệm vụ của bạn:
- Hãy sửa đổi bản dịch của các phân đoạn này để khắc phục hoàn toàn lỗi đã chỉ ra.
- KHÔNG dịch từng chữ. Đảm bảo câu thoại nghe tự nhiên khi lồng tiếng.
- TUYỆT ĐỐI KHÔNG để sót bất kỳ ký tự tiếng Trung/Nhật/Hàn (CJK) nào trong kết quả dịch.
- Đảm bảo câu thoại ngắn gọn và đọc vừa vặn trong duration được giao.
- KHÔNG thay đổi id, duration hoặc source_text của phân đoạn.

STRICT OUTPUT FORMAT:
Bạn bắt buộc phải phản hồi bằng 1 JSON object duy nhất có key "repaired_segments" chứa mảng các phân đoạn đã sửa lỗi.
Không viết thêm lời giải thích hay bọc trong markdown code fence.

Expected JSON output format:
{{
  "repaired_segments": [
    {{
      "id": 6,
      "literal_vi": "bản dịch nghĩa chính xác",
      "dub_vi": "bản lời thoại đã sửa lỗi hoàn toàn sạch ký tự gốc và tự nhiên",
      "speaker": "tên nhân vật",
      "speaker_gender": "male/female/neutral"
    }}
  ]
}}

VIDEO_CONTEXT:
{json.dumps(video_context, ensure_ascii=False, indent=2)}

GLOSSARY:
{json.dumps(glossary, ensure_ascii=False, indent=2)}

CHARACTER_BIBLE:
{json.dumps(character_bible, ensure_ascii=False, indent=2)}

SEGMENTS_TO_REPAIR (Chỉ sửa các phân đoạn này):
{json.dumps(repaired_input, ensure_ascii=False, indent=2)}
"""
    return prompt


def repair_gemini(prompt: str) -> list[dict] | None:
    from src.utils import call_gemini_api
    res_text = call_gemini_api(prompt, temperature=0.1)
    if res_text:
        try:
            cleaned = res_text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            data = json.loads(cleaned)
            return data.get("repaired_segments")
        except Exception as e:
            logger.error(f"Failed to parse Gemini repair json: {e}")
    return None


def repair_groq(prompt: str) -> list[dict] | None:
    from src.utils import call_groq_api
    res_text = call_groq_api(prompt, temperature=0.1)
    if res_text:
        try:
            cleaned = res_text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            data = json.loads(cleaned)
            return data.get("repaired_segments")
        except Exception as e:
            logger.error(f"Failed to parse Groq repair json: {e}")
    return None


def repair_translation(
    segments: list[dict],
    issues: list[dict],
    video_context: dict,
    glossary: dict,
    character_bible: dict,
    output_path: str = None
) -> list[dict]:
    """Repairs segments with critical errors (severity='error') and returns updated segments."""
    # Find segments that have errors
    bad_ids = {iss["id"] for iss in issues if iss["severity"] == "error" and iss["id"] > 0}
    
    if not bad_ids:
        logger.info("No critical errors found. No repair needed.")
        return segments

    logger.info(f"Critical issues found in {len(bad_ids)} segments. Initiating repair...")
    bad_segments = [s for s in segments if s["id"] in bad_ids]

    prompt = build_repair_prompt(video_context, glossary, character_bible, bad_segments, issues)
    
    repaired_results = repair_gemini(prompt)
    if not repaired_results:
        logger.info("Gemini repair failed, trying Groq fallback...")
        repaired_results = repair_groq(prompt)

    if not repaired_results:
        logger.error("All AI translation repair attempts failed.")
        # Create fallback repair report
        report = {
            "repaired_count": 0,
            "status": "failed",
            "details": "AI API error during repair phase"
        }
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        return segments

    # Merge repaired segments back
    repaired_map = {item["id"]: item for item in repaired_results}
    updated_segments = []
    
    repaired_log = []

    for s in segments:
        seg_id = s["id"]
        if seg_id in repaired_map:
            rep = repaired_map[seg_id]
            
            dub_vi = rep.get("dub_vi", s["dub_vi"])
            cleaned_text = re.sub(r"[^\w\s\d,.\-!?]", "", dub_vi).strip()
            if not cleaned_text:
                dub_vi = "Hả."

            logger.info(f"  Repaired Segment {seg_id}: '{s['dub_vi']}' -> '{dub_vi}'")
            
            repaired_log.append({
                "id": seg_id,
                "original": s["dub_vi"],
                "repaired": dub_vi
            })

            updated_segments.append({
                **s,
                "literal_vi": rep.get("literal_vi", s["literal_vi"]),
                "dub_vi": dub_vi,
                "text_vi": dub_vi,  # Maintain backwards compatibility
                "speaker": rep.get("speaker", s["speaker"]),
                "speaker_gender": rep.get("speaker_gender", s["speaker_gender"]),
                "risk_flags": s.get("risk_flags", []) + ["REPAIRED"]
            })
        else:
            updated_segments.append(s)

    report = {
        "repaired_count": len(repaired_log),
        "status": "success",
        "details": repaired_log
    }

    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved translation repair report to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save translation repair report: {e}")

    return updated_segments
