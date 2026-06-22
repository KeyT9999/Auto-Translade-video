"""Glossary Builder — Generates glossary.json from transcript and video context."""

from __future__ import annotations

from copy import deepcopy
import json
import os

from src.glossary_enforcer import sanitize_glossary
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
        "他们": "họ / bọn họ",
    }
}


def _merge_default_terms(glossary: dict | None) -> dict:
    merged = deepcopy(glossary) if isinstance(glossary, dict) else {}
    terms = dict(DEFAULT_GLOSSARY["terms"])
    if isinstance(merged.get("terms"), dict):
        terms.update(merged["terms"])
    merged["terms"] = terms
    return merged


def _save_glossary(output_path: str, glossary: dict) -> None:
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(glossary, handle, ensure_ascii=False, indent=2)


def build_glossary_prompt(segments: list[dict], video_context: dict) -> str:
    sample = segments[:100]
    transcript_text = "\n".join(f"[{s['id']}] {s.get('text', '')}" for s in sample)

    return f"""You are building a bilingual glossary mapping for translating a video transcript into natural Vietnamese.
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


def build_glossary(segments: list[dict], video_context: dict, output_path: str) -> dict:
    """Build and save glossary.json."""
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as handle:
                glossary = sanitize_glossary(_merge_default_terms(json.load(handle)))
            logger.info("Loaded existing glossary from %s", output_path)
            _save_glossary(output_path, glossary)
            return glossary
        except Exception as exc:
            logger.warning("Failed to read existing glossary: %s", exc)

    logger.info("Generating new glossary...")
    prompt = build_glossary_prompt(segments, video_context)

    from src.ai import ai_router

    try:
        glossary = ai_router.generate_glossary(prompt)
    except Exception as exc:
        logger.error("Router failed to generate glossary: %s", exc)
        glossary = None

    if not glossary:
        logger.warning("Failed to generate glossary via LLMs, using default glossary fallback.")
        glossary = deepcopy(DEFAULT_GLOSSARY)

    if "terms" not in glossary or not isinstance(glossary["terms"], dict):
        glossary = deepcopy(DEFAULT_GLOSSARY)

    glossary = sanitize_glossary(_merge_default_terms(glossary))

    try:
        _save_glossary(output_path, glossary)
        logger.info("Saved glossary to %s", output_path)
    except Exception as exc:
        logger.error("Failed to save glossary: %s", exc)

    return glossary
