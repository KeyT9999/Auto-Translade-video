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
    segments_to_translate = [
        {"id": s["id"], "text": s["text"], "duration": s["duration"]}
        for s in segments
    ]
    segments_json = json.dumps(segments_to_translate, ensure_ascii=False, indent=2)

    prompt = f"""You are translating an ASR transcript for a YouTube dub from {source_lang} to Vietnamese.
Below is a JSON array of segments to translate. Each has: id, text, duration (seconds).

STRICT OUTPUT FORMAT:
You MUST respond with a JSON object containing a single key "segments" which maps to a list.
Each item in the list must be an object with exactly two keys: "id" (integer) and "text_vi" (string, the Vietnamese translation).
Do not return any other text, explanation, or markdown formatting outside of the JSON object.

Example output structure:
{{
  "segments": [
    {{
      "id": 1,
      "text_vi": "Xin chào mọi người."
    }}
  ]
}}

STYLE RULES:
- Use "bạn" / "mình" / "các bạn" for pronouns (never "mày/tao", "ông/bà").
- Use casual YouTube-creator tone, direct, natural, and skip filler words.
- Brand names: keep them original (e.g. Mercedes, Samsung).
- Sino-Vietnamese names: only when everyday/natural.
- Chinese names -> pinyin (e.g. 方太谢 -> Fang Tai-xie).
- Korean drama/actor names -> Korean Romanization (e.g. 朱志勋 -> Joo Ji-hoon).
- Drop Chinese discourse particles (啊/呢/嘛/吧).
- Bleeped/censored segments (e.g. "**"): use a short Vietnamese exclamation like "Hả." or "Á." (DO NOT output "..." or empty string).

DURATION-AWARE LENGTH (CRITICAL):
- Each segment has a duration. The Vietnamese spoken audio MUST fit within this duration window.
- Spoken pace: ~12 chars/sec normal, ~15 chars/sec max at 1.3x speed.
- Short duration (<4s): use the shortest natural phrasing.
- Medium duration (4-8s): natural casual speech, prefer shorter synonyms.
- Long duration (>8s): more room, but still keep it concise.
- When in doubt, prefer the SHORTER Vietnamese phrasing.

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

    logger.info(f"Successfully translated {len(updated_segments)} segments.")
    return updated_segments
