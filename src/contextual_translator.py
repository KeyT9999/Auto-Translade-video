"""Context-aware Translator — Translates segments using a sliding window and context/glossary/bible profile."""
import json
import os
import re
import time
import requests
import config
from src.utils import setup_logging

logger = setup_logging("contextual_translator")

WINDOW_SIZE = 25
CONTEXT_SIZE = 3


def build_window_prompt(
    video_context: dict,
    glossary: dict,
    character_bible: dict,
    prev_segs: list[dict],
    target_segs: list[dict],
    next_segs: list[dict],
    source_lang: str
) -> str:
    # Build clean representations for prompt
    def clean_segs(segs):
        return [{"id": s["id"], "text": s["text"], "duration": s["duration"]} for s in segs]

    prev_json = json.dumps(clean_segs(prev_segs), ensure_ascii=False, indent=2)
    target_json = json.dumps(clean_segs(target_segs), ensure_ascii=False, indent=2)
    next_json = json.dumps(clean_segs(next_segs), ensure_ascii=False, indent=2)

    prompt = f"""Bạn là biên dịch viên chuyên nghiệp lồng tiếng video từ {source_lang} sang tiếng Việt.

Nhiệm vụ:
- Dịch các segment trong TARGET_SEGMENTS sang tiếng Việt tự nhiên, phù hợp để lồng tiếng (TTS/dubbing).
- Sử dụng PREVIOUS_SEGMENTS và NEXT_SEGMENTS để hiểu mạch ngữ cảnh hội thoại, KHÔNG ĐƯỢC dịch các segment này.
- KHÔNG dịch từng chữ máy móc. Ưu tiên câu thoại ngắn gọn, văn phong nói tự nhiên.
- Dùng đúng xưng hô nhân vật theo CHARACTER_BIBLE.
- Tuân thủ để lại deixis policy và dịch thuật ngữ trong GLOSSARY (Ví dụ các từ chỉ vị trí: 这里, 这边, 楼上, 下面,...).
- TUYỆT ĐỐI KHÔNG để sót bất kỳ ký tự tiếng Trung/Nhật/Hàn (CJK) nào trong literal_vi, dub_vi hoặc text_vi.
- Phù hợp với duration từng segment. Nếu câu dịch quá dài, hãy rút ngắn tự nhiên. Nếu câu gốc quá ngắn so với duration, có thể thêm từ đệm biểu cảm tự nhiên (nhé, nha, nào,...) nhưng không bịa thêm thông tin sai lệch.

STRICT OUTPUT FORMAT:
Bạn bắt buộc phải phản hồi bằng 1 JSON object duy nhất có key "segments" chứa mảng kết quả của TARGET_SEGMENTS.
Không viết thêm lời giải thích hay bọc trong markdown code fence.

Expected JSON output format:
{{
  "segments": [
    {{
      "id": 1,
      "source_text": "text gốc",
      "literal_vi": "bản dịch nghĩa chính xác từng từ/câu",
      "dub_vi": "bản lời thoại lồng tiếng Việt tối ưu cho phát âm TTS",
      "speaker": "SPEAKER_00 hoặc tên nhân vật tương ứng",
      "speaker_gender": "male / female / neutral",
      "pronoun_note": "ghi chú xưng hô nhân vật",
      "context_note": "ghi chú bối cảnh nếu có",
      "risk_flags": []
    }}
  ]
}}

VIDEO_CONTEXT:
{json.dumps(video_context, ensure_ascii=False, indent=2)}

GLOSSARY:
{json.dumps(glossary, ensure_ascii=False, indent=2)}

CHARACTER_BIBLE:
{json.dumps(character_bible, ensure_ascii=False, indent=2)}

PREVIOUS_SEGMENTS (Chỉ dùng làm ngữ cảnh trước, KHÔNG dịch):
{prev_json}

TARGET_SEGMENTS (BẮT BUỘC dịch đầy đủ):
{target_json}

NEXT_SEGMENTS (Chỉ dùng làm ngữ cảnh sau, KHÔNG dịch):
{next_json}
"""
    return prompt


def translate_window_gemini(prompt: str) -> list[dict] | None:
    from src.utils import call_gemini_api
    res_text = call_gemini_api(prompt)
    if res_text:
        try:
            cleaned = res_text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            data = json.loads(cleaned)
            return data.get("segments")
        except Exception as e:
            logger.error(f"Failed to parse Gemini window json: {e}")
    return None


def translate_window_groq(prompt: str) -> list[dict] | None:
    from src.utils import call_groq_api
    res_text = call_groq_api(prompt)
    if res_text:
        try:
            cleaned = res_text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            data = json.loads(cleaned)
            return data.get("segments")
        except Exception as e:
            logger.error(f"Failed to parse Groq window json: {e}")
    return None


def translate_segments_contextual(
    segments: list[dict],
    video_context: dict,
    glossary: dict,
    character_bible: dict,
    source_lang: str
) -> list[dict]:
    """Translate ASR transcript segments using a sliding window contextual approach."""
    if not segments:
        return []

    logger.info(f"Starting contextual translation of {len(segments)} segments...")
    translated_segments = []

    for i in range(0, len(segments), WINDOW_SIZE):
        target_segs = segments[i:i + WINDOW_SIZE]
        
        # Calculate context slices
        prev_start = max(0, i - CONTEXT_SIZE)
        prev_segs = segments[prev_start:i]
        
        next_end = min(len(segments), i + WINDOW_SIZE + CONTEXT_SIZE)
        next_segs = segments[i + WINDOW_SIZE:next_end]

        logger.info(f"Translating window: segments {target_segs[0]['id']} to {target_segs[-1]['id']}")

        prompt = build_window_prompt(
            video_context, glossary, character_bible,
            prev_segs, target_segs, next_segs, source_lang
        )

        window_results = None
        # Try Gemini
        window_results = translate_window_gemini(prompt)
        
        # Fallback to Groq
        if not window_results:
            logger.info("Gemini failed/unavailable, falling back to Groq Llama for window...")
            window_results = translate_window_groq(prompt)

        # Parse and ensure structure
        if not window_results or len(window_results) != len(target_segs):
            logger.warning(f"Translation failed for window. Falling back to local translation structure mapping.")
            # Local fallback: copy original text
            window_results = []
            for s in target_segs:
                window_results.append({
                    "id": s["id"],
                    "source_text": s["text"],
                    "literal_vi": s["text"],
                    "dub_vi": s["text"],
                    "speaker": "NARRATOR",
                    "speaker_gender": "neutral",
                    "pronoun_note": "fallback",
                    "context_note": "",
                    "risk_flags": ["LLM_TRANSLATION_FAILURE"]
                })

        # Map back start, end, duration and merge results
        for orig, res in zip(target_segs, window_results):
            # Clean Vietnamese texts from source language code leak if any
            dub_vi = res.get("dub_vi", orig["text"])
            
            # Prevent empty text or pure punctuation crashes in LucyLab
            cleaned_text = re.sub(r"[^\w\s\d,.\-!?]", "", dub_vi).strip()
            if not cleaned_text:
                dub_vi = "Hả."

            translated_segments.append({
                "id": orig["id"],
                "text": orig["text"],
                "start": orig["start"],
                "end": orig["end"],
                "duration": orig["duration"],
                "literal_vi": res.get("literal_vi", orig["text"]),
                "dub_vi": dub_vi,
                "text_vi": dub_vi,  # Alias for backwards compatibility
                "speaker": res.get("speaker", "NARRATOR"),
                "speaker_gender": res.get("speaker_gender", "neutral"),
                "context_note": res.get("context_note", ""),
                "pronoun_note": res.get("pronoun_note", ""),
                "risk_flags": res.get("risk_flags", [])
            })

        # Small throttle to respect API rate limits
        time.sleep(2.0)

    logger.info(f"Contextual translation complete. Translated {len(translated_segments)} segments.")
    return translated_segments
