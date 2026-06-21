"""Timeline-aware Rewrite — Reworks Vietnamese dubbing text to match target segment durations (shortens or expands naturally)."""
import json
import os
import re
import requests
import config
from src.utils import setup_logging

logger = setup_logging("timeline_rewriter")


def build_rewrite_prompt(
    video_context: dict,
    character_bible: dict,
    segments_to_rewrite: list[dict]
) -> str:
    prompt_items = []
    for s in segments_to_rewrite:
        char_rate = len(s["dub_vi"]) / s["duration"] if s["duration"] > 0 else 0
        direction = "SHORTEN (câu thoại quá dài so với duration, hãy viết lại cực kỳ ngắn gọn)" if char_rate > 15.0 else "EXPAND (câu thoại quá ngắn so với duration, hãy thêm từ đệm tự nhiên như 'đó', 'nhé', 'nha' để lấp đầy thời gian nói mà không bịa thêm nội dung)"
        prompt_items.append({
            "id": s["id"],
            "source_text": s["text"],
            "dub_vi": s["dub_vi"],
            "duration": s["duration"],
            "direction": direction,
            "char_rate_chars_per_sec": round(char_rate, 1)
        })

    prompt = f"""Bạn là một chuyên gia lồng tiếng video. Nhiệm vụ của bạn là viết lại các câu thoại lồng tiếng tiếng Việt (dub_vi) dưới đây sao cho thời lượng nói vừa khớp với thời gian (duration) của phân cảnh.

Quy tắc:
1. Nếu direction là SHORTEN: Hãy viết lại câu thoại thật ngắn gọn, súc tích nhưng giữ nguyên ý nghĩa chính.
2. Nếu direction là EXPAND: Hãy kéo dài câu thoại bằng cách thêm các từ đệm, trợ từ nói tự nhiên trong tiếng Việt (như "đó", "nhỉ", "nhé", "nha", "đấy", "thế",...) hoặc cách nói kéo dài từ ngữ để lấp đầy thời gian cảnh mà không thêm thông tin sai lệch hay bịa chuyện.
3. TUYỆT ĐỐI KHÔNG để sót ký tự ngôn ngữ gốc CJK (tiếng Trung/Nhật/Hàn).
4. Không thay đổi id.
5. Giữ nguyên đại từ xưng hô tương ứng theo CHARACTER_BIBLE.

STRICT OUTPUT FORMAT:
Bạn bắt buộc phải phản hồi bằng 1 JSON object duy nhất có key "rewritten_segments" chứa mảng các phân đoạn đã được tối ưu timeline.
Không viết thêm lời giải thích hay bọc trong markdown code fence.

Expected JSON output format:
{{
  "rewritten_segments": [
    {{
      "id": 18,
      "final_dub_vi": "câu thoại mới đã được tối ưu hóa timeline hoàn hảo"
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
    return prompt


def rewrite_gemini(prompt: str) -> list[dict] | None:
    from src.utils import call_gemini_api
    res_text = call_gemini_api(prompt)
    if res_text:
        try:
            cleaned = res_text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            data = json.loads(cleaned)
            return data.get("rewritten_segments")
        except Exception as e:
            logger.error(f"Failed to parse Gemini rewrite json: {e}")
    return None


def rewrite_groq(prompt: str) -> list[dict] | None:
    from src.utils import call_groq_api
    res_text = call_groq_api(prompt)
    if res_text:
        try:
            cleaned = res_text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            data = json.loads(cleaned)
            return data.get("rewritten_segments")
        except Exception as e:
            logger.error(f"Failed to parse Groq rewrite json: {e}")
    return None


def rewrite_timeline(
    segments: list[dict],
    video_context: dict,
    character_bible: dict
) -> list[dict]:
    """Identify segments that need adjustment, call AI to rewrite them, and return updated list."""
    to_rewrite = []
    for s in segments:
        dub_vi = s.get("dub_vi", "")
        duration = s.get("duration", 0.0)
        if not dub_vi or duration <= 0:
            continue
        
        char_rate = len(dub_vi) / duration
        # Too long: > 15 chars/sec
        # Too short: < 6 chars/sec and duration > 4 seconds
        if char_rate > 15.0 or (char_rate < 6.0 and duration > 4.0):
            to_rewrite.append(s)

    if not to_rewrite:
        logger.info("No segments need timing adjustment.")
        for s in segments:
            s["timing_rewrite_applied"] = False
            s["original_dub_vi"] = s.get("dub_vi", "")
            s["final_dub_vi"] = s.get("dub_vi", "")
        return segments

    logger.info(f"Found {len(to_rewrite)} segments requiring timeline rewrite.")
    prompt = build_rewrite_prompt(video_context, character_bible, to_rewrite)

    rewritten_results = rewrite_gemini(prompt)
    if not rewritten_results:
        logger.info("Gemini timeline rewrite failed, trying Groq Llama fallback...")
        rewritten_results = rewrite_groq(prompt)

    if not rewritten_results:
        logger.warning("Timeline rewrite AI failed. Proceeding with original translations.")
        for s in segments:
            s["timing_rewrite_applied"] = False
            s["original_dub_vi"] = s.get("dub_vi", "")
            s["final_dub_vi"] = s.get("dub_vi", "")
        return segments

    rewritten_map = {item["id"]: item.get("final_dub_vi", "") for item in rewritten_results}
    updated_segments = []

    for s in segments:
        seg_id = s["id"]
        original_dub = s.get("dub_vi", "")
        if seg_id in rewritten_map and rewritten_map[seg_id]:
            final_dub = rewritten_map[seg_id]
            # Ensure not empty
            cleaned_text = re.sub(r"[^\w\s\d,.\-!?]", "", final_dub).strip()
            if not cleaned_text:
                final_dub = original_dub
            
            logger.info(f"  Timeline rewritten segment {seg_id}: '{original_dub}' -> '{final_dub}'")
            updated_segments.append({
                **s,
                "timing_rewrite_applied": True,
                "original_dub_vi": original_dub,
                "dub_vi": final_dub,
                "final_dub_vi": final_dub,
                "text_vi": final_dub  # Alias for backward compatibility
            })
        else:
            updated_segments.append({
                **s,
                "timing_rewrite_applied": False,
                "original_dub_vi": original_dub,
                "final_dub_vi": original_dub
            })

    return updated_segments
