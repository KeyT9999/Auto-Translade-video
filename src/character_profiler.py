"""Character Profiler — Generates character_bible.json for translation consistency."""

from __future__ import annotations

from copy import deepcopy
import json
import os

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
            "voice_id": None,
        }
    ],
    "global_pronoun_rules": {
        "我们": "mình / chúng mình",
        "你": "bạn / mọi người",
        "他": "người đó / anh ấy tùy ngữ cảnh",
        "她": "người đó / cô ấy tùy ngữ cảnh",
    },
}


def sanitize_character_bible(bible: dict | None) -> dict:
    if not isinstance(bible, dict):
        return deepcopy(DEFAULT_BIBLE)

    sanitized = deepcopy(bible)
    default_character = DEFAULT_BIBLE["characters"][0]

    characters = []
    for raw_character in sanitized.get("characters", []):
        if not isinstance(raw_character, dict):
            continue
        character = {**deepcopy(default_character), **raw_character}
        character["vi_pronoun_self"] = str(character.get("vi_pronoun_self") or "mình").strip()
        character["vi_pronoun_other"] = str(character.get("vi_pronoun_other") or "bạn").strip()
        characters.append(character)

    if not characters:
        characters = deepcopy(DEFAULT_BIBLE["characters"])

    rules = dict(DEFAULT_BIBLE["global_pronoun_rules"])
    raw_rules = sanitized.get("global_pronoun_rules", {})
    if isinstance(raw_rules, dict):
        for source_pronoun, target_pronoun in raw_rules.items():
            target_text = str(target_pronoun or "").strip()
            if target_text:
                rules[str(source_pronoun)] = target_text

    sanitized["characters"] = characters
    sanitized["global_pronoun_rules"] = rules
    return sanitized


def _save_character_bible(output_path: str, bible: dict) -> None:
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(bible, handle, ensure_ascii=False, indent=2)


def build_profiler_prompt(segments: list[dict], video_context: dict) -> str:
    sample = segments[:120]
    transcript_text = "\n".join(f"[{s['id']}] {s.get('text', '')}" for s in sample)

    return f"""You are building a character profile ("character bible") for a video to ensure consistent pronoun usage in Vietnamese translation.
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


def build_character_bible(segments: list[dict], video_context: dict, output_path: str) -> dict:
    """Build and save character_bible.json."""
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as handle:
                bible = sanitize_character_bible(json.load(handle))
            logger.info("Loaded existing character bible from %s", output_path)
            _save_character_bible(output_path, bible)
            return bible
        except Exception as exc:
            logger.warning("Failed to read existing character bible: %s", exc)

    logger.info("Generating new character bible...")
    prompt = build_profiler_prompt(segments, video_context)

    from src.ai import ai_router

    try:
        bible = ai_router.generate_character_bible(prompt)
    except Exception as exc:
        logger.error("Router failed to generate character bible: %s", exc)
        bible = None

    if not bible:
        logger.warning("Failed to generate character bible via LLMs, using default fallback.")
        bible = deepcopy(DEFAULT_BIBLE)

    bible = sanitize_character_bible(bible)

    try:
        _save_character_bible(output_path, bible)
        logger.info("Saved character bible to %s", output_path)
    except Exception as exc:
        logger.error("Failed to save character bible: %s", exc)

    return bible
