"""Glossary Builder — Generates glossary.json from transcript and video context using Gemini/Groq."""
import json
import os
from src.utils import setup_logging

logger = setup_logging("glossary_builder")

DEFAULT_GLOSSARY = {
    "terms": {
        "这里": "ở đây / chỗ này",
        "这边": "bên này / phía này",
        "楼上": "tầng trên / phía trên",
        "下面": "bên dưới / phía dưới",
        "坐": "đi / lên (thang máy, xe)",
        "电梯": "thang máy",
        "前台": "quầy lễ tân",
        "楼": "tầng / lầu",
        "咖啡厅": "quán cà phê",
        "我们": "mình / chúng mình",
        "你们": "các bạn / mọi người",
        "他们": "họ / bọn họ"
    }
}


def build_glossary_prompt(segments: list[dict], video_context: dict) -> str:
    sample = segments[:100]
    transcript_text = "\n".join([f"[{s['id']}] {s.get('text', '')}" for s in sample])

    prompt = f"""You are building a bilingual glossary mapping for translating a video transcript into natural Vietnamese.
Context of the video:
Type: {video_context.get('video_type', 'unknown')}
Topic: {video_context.get('topic', 'unknown')}
Setting: {video_context.get('setting', 'unknown')}
Tone: {video_context.get('tone', 'unknown')}

Task:
Identify important nouns, technical terms, locations, or frequent words (such as '这里', '这边', '楼上', '下面', '电梯', '前台', '咖啡厅', '坐' in Chinese transcripts) in the transcript below.
For each, provide a natural Vietnamese translation that fits the video context.
Avoid overly formal or literal translations. For example:
- In vlog context, '这里' should map to 'ở đây' or 'chỗ này' instead of 'nơi này'.
- In elevator context, '坐电梯' should map to 'đi thang máy' or 'lên thang máy'.
- In locations, '楼上' should map to 'tầng trên' or 'lầu trên'.

STRICT OUTPUT FORMAT:
You MUST respond with a single JSON object. Do not wrap in markdown fences or write explanations.

Expected JSON schema:
{{
  "terms": {{
    "source_term_1": "vietnamese_translation_1",
    "source_term_2": "vietnamese_translation_2"
  }}
}}

Transcript lines:
{transcript_text}
"""
    return prompt
def build_glossary(segments: list[dict], video_context: dict, output_path: str) -> dict:
    """Build and save glossary.json."""
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                glossary = json.load(f)
                logger.info(f"Loaded existing glossary from {output_path}")
                return glossary
        except Exception as e:
            logger.warning(f"Failed to read existing glossary: {e}")

    logger.info("Generating new glossary...")
    prompt = build_glossary_prompt(segments, video_context)

    from src.ai import ai_router
    try:
        glossary = ai_router.generate_glossary(prompt)
    except Exception as e:
        logger.error(f"Router failed to generate glossary: {e}")
        glossary = None

    if not glossary:
        logger.warning("Failed to generate glossary via LLMs, using default glossary fallback.")
        glossary = DEFAULT_GLOSSARY.copy()

    # Ensure required structure and merge defaults
    if "terms" not in glossary or not isinstance(glossary["terms"], dict):
        glossary = DEFAULT_GLOSSARY.copy()
    else:
        # Merge default terms if not present
        for k, v in DEFAULT_GLOSSARY["terms"].items():
            if k not in glossary["terms"]:
                glossary["terms"][k] = v

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(glossary, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved glossary to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save glossary: {e}")

    return glossary
