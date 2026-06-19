import json
import os
import re
import time
import requests
import config
from src.utils import setup_logging

logger = setup_logging("translator")


def build_translation_prompt(segments: list[dict], source_lang: str) -> str:
    # Minimize data sent to LLM to save tokens and prevent truncation
    # Pass speaker and speaker_gender if present.
    segments_to_translate = []
    for s in segments:
        seg = {"id": s["id"], "text": s["text"], "duration": s["duration"]}
        if "speaker" in s:
            seg["speaker"] = s["speaker"]
        if "speaker_gender" in s:
            seg["speaker_gender"] = s["speaker_gender"]
        segments_to_translate.append(seg)
        
    segments_json = json.dumps(segments_to_translate, ensure_ascii=False, indent=2)

    prompt = f"""You are translating an ASR transcript of a short Chinese drama video (or dialogue-heavy video) from {source_lang} to Vietnamese.
Below is a JSON array of segments to translate. Each has: id, text, duration (seconds), and optionally speaker / speaker_gender.

STRICT OUTPUT FORMAT:
You MUST respond with a JSON object containing a single key "segments" which maps to a list.
Each item in the list must be an object with exactly two keys: "id" (integer) and "text_vi" (string, the Vietnamese translation).
Do not return any other text, explanation, or markdown formatting outside of the JSON object.

Example output structure:
{{
  "segments": [
    {{
      "id": 1,
      "text_vi": "Con thích bố hay mẹ hơn?"
    }}
  ]
}}

VIETNAMESE PRONOUN SYSTEM (CRITICAL):
Determine appropriate Vietnamese pronouns (xưng hô) based on the dialogue context, speaker roles, and genders.
- If speaker info (e.g. "speaker": "ME", "speaker_gender": "female") is provided in the JSON, use it to guide pronoun selection.
- If speaker info is not provided, you MUST analyze the relationship and roles from the context of the conversation.
- Common drama relationships and correct xưng hô (speaker speaks to listener):
  * Mother to child (ME -> CON): "mẹ" - "con"
  * Child to mother (CON -> ME): "con" - "mẹ"
  * Aunt/older female to niece/nephew (DÌ/CÔ -> CON/CHÁU): "dì"/"cô" - "con"
  * Niece/nephew to aunt/older female (CON/CHÁU -> DÌ/CÔ): "con" - "dì"/"cô"
  * Husband and wife: "anh" - "em"
  * Friends / peers: "tớ" - "cậu", "mình" - "bạn", or "tao" - "mày" (if angry/very informal)
  * Older sister to younger sibling: "chị" - "em"
  * Younger sibling to older sister: "em" - "chị"
- TUYỆT ĐỐI KHÔNG (NEVER) use generic "bạn" / "tôi" in family drama contexts (e.g., between mother, daughter, aunt, child). It sounds extremely unnatural and robotic.

NATURAL VIETNAMESE DIALOGUE STYLE:
- Translate the MEANING and EMOTION, not word-for-word.
- Use natural spoken Vietnamese phrasing (văn nói), NOT formal or literary writing.
- TUYỆT ĐỐI KHÔNG use Chinese transliterations (e.g., do NOT translate as "hảo", "mua mua", "aiya", "hảo mua mua", "lão công"). Translate the actual meaning (e.g., "hảo" -> "tốt/được", "lão công" -> "chồng", "mua mua" -> sounds of kissing or sweet talking like "cưng quá").
- Drop Chinese discourse particles (啊/呢/嘛/吧/hoặc/嗯/ô/um).
- Retain the emotional tone (sarcasm, teasing, anger, affection, panic, grief).
- Bleeped/censored segments (e.g. "**"): use a short Vietnamese exclamation/word like "Hả." or "Cái gì." or "Chết tiệt." (DO NOT output "..." or empty string).

DURATION-AWARE LENGTH (CRITICAL):
- Each segment has a duration. The Vietnamese spoken audio MUST fit within this duration window.
- Spoken pace: ~12 chars/sec normal, ~15 chars/sec max.
- Short duration (<4s): use the shortest natural phrasing.
- Medium duration (4-8s): natural casual speech, prefer shorter synonyms.
- Long duration (>8s): more room, but still keep it concise.
- When in doubt, prefer the SHORTER Vietnamese phrasing to avoid overlap.

Segments to translate:
{segments_json}
"""
    return prompt


def parse_translation_response(response_text: str) -> dict:
    """Clean markdown blocks and parse JSON response."""
    cleaned = response_text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def translate_gemini(prompt: str) -> dict | None:
    if not config.GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY not set. Skipping Gemini translation.")
        return None

    try:
        from google import genai
        from google.genai import types

        logger.info("Calling Gemini 2.0 Flash for translation...")
        client = genai.Client(api_key=config.GOOGLE_API_KEY)
        
        # Use gemini-2.0-flash as primary
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )
        if response.text:
            return parse_translation_response(response.text)
        return None
    except Exception as e:
        logger.error(f"Gemini translation failed: {e}")
        return None


def translate_groq(prompt: str) -> dict | None:
    if not config.GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set. Skipping Groq translation.")
        return None

    try:
        logger.info("Calling Groq Llama 3.3 70B for translation...")
        headers = {
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise JSON translation assistant."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return parse_translation_response(content)
    except Exception as e:
        logger.error(f"Groq translation failed: {e}")
        return None


def post_check_translation(segments: list[dict]) -> None:
    """Check translated segments for common quality issues and log warnings.
    Non-blocking, for logging purposes only.
    """
    family_speakers = {"ME", "CON", "DÌ", "CÔ", "MẸ", "BỐ", "CHA", "CHÁU", "ÔNG", "BÀ"}
    # Words/phrases representing Chinese transliterations or leftovers
    chinese_slang_pattern = re.compile(r"\b(aiya|ai\s+ya|mua\s+mua|hảo\s+mua\s+mua)\b", re.IGNORECASE)
    # Chinese characters range
    chinese_chars_pattern = re.compile(r"[\u4e00-\u9fff]")

    for s in segments:
        seg_id = s.get("id")
        text_orig = s.get("text", "")
        text_vi = s.get("text_vi", "")
        duration = s.get("duration", 0.0)
        speaker = s.get("speaker", "")

        # 1. Family speaker check for "bạn" / "tôi"
        if speaker and speaker.upper() in family_speakers:
            for word in ["bạn", "tôi"]:
                if re.search(rf"\b{word}\b", text_vi, re.IGNORECASE):
                    logger.warning(
                        f"Segment {seg_id}: Speaker '{speaker}' translation '{text_vi}' "
                        f"contains inappropriate family pronoun '{word}'."
                    )

        # 2. Chinese slang/transliteration check
        if chinese_slang_pattern.search(text_vi):
            logger.warning(
                f"Segment {seg_id}: Translation '{text_vi}' contains suspected Chinese transliteration."
            )

        # 3. Leftover Chinese characters check
        if chinese_chars_pattern.search(text_vi):
            logger.warning(
                f"Segment {seg_id}: Translation '{text_vi}' contains leftover Chinese characters."
            )

        # 4. Isolated "hảo" check
        hảo_matches = re.finditer(r"\bhảo\b", text_vi, re.IGNORECASE)
        for m in hảo_matches:
            start, end = m.start(), m.end()
            hảo_hảo_pattern = re.compile(r"\bhảo\s+hảo\b", re.IGNORECASE)
            is_part_of_hao_hao = False
            for hh_m in hảo_hảo_pattern.finditer(text_vi):
                if hh_m.start() <= start <= hh_m.end():
                    is_part_of_hao_hao = True
                    break
            if not is_part_of_hao_hao:
                logger.warning(
                    f"Segment {seg_id}: Translation '{text_vi}' contains isolated word 'hảo' "
                    f"(often Chinese transliteration of 好)."
                )

        # 5. Char rate check (>15 chars/sec)
        if duration > 0:
            char_rate = len(text_vi) / duration
            if char_rate > 15.0:
                logger.warning(
                    f"Segment {seg_id}: Translation '{text_vi}' has high character rate "
                    f"({char_rate:.1f} chars/sec, duration {duration}s), might not fit in audio."
                )

        # 6. Untranslated check (too similar to original text)
        if text_orig and any(c.isalpha() for c in text_orig):
            clean_orig = re.sub(r"[^\w\s]", "", text_orig).strip().lower()
            clean_vi = re.sub(r"[^\w\s]", "", text_vi).strip().lower()
            if clean_orig == clean_vi and len(clean_orig) > 2:
                logger.warning(
                    f"Segment {seg_id}: Translation is identical to original text: '{text_vi}'."
                )


def translate_segments(segments: list[dict], source_lang: str) -> list[dict]:
    """Translate ASR transcript segments into Vietnamese using Gemini/Groq.

    Returns the original segments list updated with 'text_vi' fields.
    """
    if not segments:
        return []

    prompt = build_translation_prompt(segments, source_lang)
    result = None

    # 1. Try Gemini first
    result = translate_gemini(prompt)

    # 2. Fall back to Groq Llama 3.3 70B
    if not result:
        logger.info("Gemini translation failed/unavailable. Falling back to Groq...")
        result = translate_groq(prompt)

    if not result or "segments" not in result:
        raise RuntimeError("Failed to obtain translation from both Gemini and Groq APIs.")

    # Match translations back to segments by ID
    translation_map = {item["id"]: item["text_vi"] for item in result["segments"]}

    updated_segments = []
    for s in segments:
        seg_id = s["id"]
        # Fall back to original text if missing from translation map
        text_vi = translation_map.get(seg_id, s["text"])
        
        # Ensure TTS text doesn't contain pure punctuation/empty to prevent LucyLab crashes
        cleaned_text = re.sub(r"[^\w\s\d,.\-!?]", "", text_vi).strip()
        if not cleaned_text:
            text_vi = "Hả."  # Default exclamation fallback

        updated_segments.append({
            **s,
            "text_vi": text_vi
        })

    # Run post-translation checks (non-blocking validation)
    try:
        post_check_translation(updated_segments)
    except Exception as e:
        logger.error(f"Error running post-translation validation: {e}")

    logger.info(f"Successfully translated {len(updated_segments)} segments.")
    return updated_segments
