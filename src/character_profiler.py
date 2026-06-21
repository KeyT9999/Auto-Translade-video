"""Character Profiler — Generates character_bible.json from transcript and video context using Gemini/Groq."""
import json
import os
import re
import requests
import config
from src.utils import setup_logging

logger = setup_logging("character_profiler")

DEFAULT_BIBLE = {
    "characters": [
        {
            "speaker_id": "NARRATOR",
            "role": "narrator",
            "gender": "neutral",
            "age": "unknown",
            "personality": "natural",
            "vi_pronoun_self": "mình",
            "vi_pronoun_other": "mọi người",
            "voice_id": None
        }
    ],
    "global_pronoun_rules": {
        "我们": "mình / chúng mình",
        "你": "bạn / mọi người",
        "他": "người đó / anh ấy tùy ngữ cảnh",
        "她": "người đó / cô ấy tùy ngữ cảnh"
    }
}


def build_profiler_prompt(segments: list[dict], video_context: dict) -> str:
    sample = segments[:120]
    transcript_text = "\n".join([f"[{s['id']}] {s.get('text', '')}" for s in sample])

    prompt = f"""You are building a character profile ("character bible") for a video to ensure consistent pronoun usage in Vietnamese translation.
Context of the video:
Type: {video_context.get('video_type', 'unknown')}
Topic: {video_context.get('topic', 'unknown')}
Setting: {video_context.get('setting', 'unknown')}

Task:
Identify all distinct speakers/characters in the transcript below.
If it is a single-speaker vlog/tutorial, create only one narrator character.
For each character, determine:
1. `speaker_id` (e.g. NARRATOR, SPEAKER_00, SPEAKER_01 or role-based like ME, CON, NV_CHINH, NV_PHU).
2. `role` (e.g. narrator, mother, child, employee, host, friend).
3. `gender` (male, female, neutral, or unknown).
4. `age` (child, young, adult, elderly, unknown).
5. `personality` (friendly, polite, angry, professional, casual).
6. `vi_pronoun_self` (how they refer to themselves in Vietnamese, e.g., 'mình', 'em', 'anh', 'mẹ', 'con', 'tôi').
7. `vi_pronoun_other` (how they refer to the listener, e.g., 'mọi người', 'bạn', 'anh', 'chị', 'con', 'mẹ').

Also define global pronoun translation rules mapping source pronouns (like 我们, 你, 他, 她) to suitable Vietnamese equivalents based on context.

STRICT OUTPUT FORMAT:
You MUST respond with a single JSON object. Do not wrap in markdown fences or write explanations.

Expected JSON schema:
{{
  "characters": [
    {{
      "speaker_id": "SPEAKER_00",
      "role": "narrator",
      "gender": "male",
      "age": "adult",
      "personality": "friendly",
      "vi_pronoun_self": "mình",
      "vi_pronoun_other": "mọi người",
      "voice_id": null
    }}
  ],
  "global_pronoun_rules": {{
    "我们": "mình / chúng mình",
    "你": "bạn / mọi người",
    "他": "người đó / anh ấy"
  }}
}}

Transcript lines:
{transcript_text}
"""
    return prompt


def generate_bible_gemini(prompt: str) -> dict | None:
    from src.utils import call_gemini_api
    res_text = call_gemini_api(prompt)
    if res_text:
        try:
            cleaned = res_text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            return json.loads(cleaned)
        except Exception as e:
            logger.error(f"Failed to parse Gemini character bible json: {e}")
    return None


def generate_bible_groq(prompt: str) -> dict | None:
    from src.utils import call_groq_api
    res_text = call_groq_api(prompt)
    if res_text:
        try:
            cleaned = res_text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            return json.loads(cleaned)
        except Exception as e:
            logger.error(f"Failed to parse Groq character bible json: {e}")
    return None


def build_character_bible(segments: list[dict], video_context: dict, output_path: str) -> dict:
    """Build and save character_bible.json."""
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                bible = json.load(f)
                logger.info(f"Loaded existing character bible from {output_path}")
                return bible
        except Exception as e:
            logger.warning(f"Failed to read existing character bible: {e}")

    logger.info("Generating new character bible...")
    prompt = build_profiler_prompt(segments, video_context)

    # Try Gemini first, fallback to Groq
    bible = generate_bible_gemini(prompt)
    if not bible:
        bible = generate_bible_groq(prompt)

    if not bible:
        logger.warning("Failed to generate character bible via LLMs, using default fallback.")
        bible = DEFAULT_BIBLE.copy()

    # Verify and merge defaults if empty
    if "characters" not in bible or not isinstance(bible["characters"], list) or not bible["characters"]:
        bible = DEFAULT_BIBLE.copy()

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(bible, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved character bible to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save character bible: {e}")

    return bible
