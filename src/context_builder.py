"""Context Builder — Generates video_context.json from transcript_original.json using Gemini/Groq."""
import json
import os
import re
import requests
import config
from src.utils import setup_logging

logger = setup_logging("context_builder")

DEFAULT_CONTEXT = {
    "video_type": "vlog",
    "topic": "general",
    "setting": "unknown",
    "speaker_style": "natural",
    "narration_pov": "first-person",
    "tone": "neutral",
    "translation_style": "natural spoken Vietnamese",
    "entities": [],
    "deixis_policy": {
        "这里": "ở đây / chỗ này",
        "这边": "bên này / phía này",
        "楼上": "tầng trên / phía trên",
        "下面": "bên dưới / phía dưới"
    },
    "pronoun_policy": {
        "self": "mình",
        "other": "mọi người"
    }
}


def build_context_prompt(segments: list[dict]) -> str:
    # Limit transcript size to avoid token overflow
    sample = segments[:100]
    transcript_text = "\n".join([f"[{s['id']}] {s.get('text', '')}" for s in sample])

    prompt = f"""You are analyzing a video transcript to construct a contextual translation profile.
Analyze the transcript below and generate a JSON object describing the video context.

STRICT OUTPUT FORMAT:
You MUST respond with a single JSON object. Do not wrap in markdown fences or write explanations.

Expected JSON schema:
{{
  "video_type": "vlog | movie | drama | news | tutorial | advertisement | unknown",
  "topic": "short description of topic",
  "setting": "short description of location/setting",
  "speaker_style": "formal | casual | energetic | emotional | narrator",
  "narration_pov": "first-person | third-person | dialogue-only | unknown",
  "tone": "humorous | serious | technical | casual | dramatic",
  "translation_style": "natural spoken Vietnamese, avoiding overly formal words",
  "entities": ["list", "of", "important", "names", "or", "terms"],
  "deixis_policy": {{
    "这里": "vietnamese translation for 'here' in this setting, e.g., 'ở đây' or 'chỗ này'",
    "这边": "vietnamese translation for 'this side'/'here', e.g., 'bên này' or 'phía này'",
    "楼上": "vietnamese translation for 'upstairs', e.g., 'tầng trên' or 'phía trên'",
    "下面": "vietnamese translation for 'downstairs'/'below', e.g., 'bên dưới' or 'tầng dưới'"
  }},
  "pronoun_policy": {{
    "self": "recommended self-pronoun, e.g., 'mình', 'em', 'anh', 'tôi'",
    "other": "recommended listener-pronoun, e.g., 'mọi người', 'bạn', 'các bạn'"
  }}
}}

Transcript lines:
{transcript_text}
"""
    return prompt


def generate_context_gemini(prompt: str) -> dict | None:
    from src.utils import call_gemini_api
    res_text = call_gemini_api(prompt)
    if res_text:
        try:
            cleaned = res_text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            return json.loads(cleaned)
        except Exception as e:
            logger.error(f"Failed to parse Gemini context json: {e}")
    return None


def generate_context_groq(prompt: str) -> dict | None:
    from src.utils import call_groq_api
    res_text = call_groq_api(prompt)
    if res_text:
        try:
            cleaned = res_text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            return json.loads(cleaned)
        except Exception as e:
            logger.error(f"Failed to parse Groq context json: {e}")
    return None


def build_video_context(segments: list[dict], output_path: str) -> dict:
    """Build and save video_context.json from transcript segments."""
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                context = json.load(f)
                logger.info(f"Loaded existing video context from {output_path}")
                return context
        except Exception as e:
            logger.warning(f"Failed to read existing video context: {e}")

    logger.info("Generating new video context...")
    prompt = build_context_prompt(segments)

    # Try Gemini first, fallback to Groq
    context = generate_context_gemini(prompt)
    if not context:
        context = generate_context_groq(prompt)

    if not context:
        logger.warning("Failed to generate context via LLMs, using default context fallback.")
        context = DEFAULT_CONTEXT.copy()

    # Ensure required fields are present
    for k, v in DEFAULT_CONTEXT.items():
        if k not in context:
            context[k] = v

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(context, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved video context to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save video context: {e}")

    return context
