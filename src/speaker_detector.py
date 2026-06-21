"""Speaker detection module — Step 4.5 in the Vietnamese dubbing pipeline.

Analyzes the translated transcript and assigns a speaker label + gender to
each segment using a single LLM call (Gemini first, Groq fallback).

Output per segment:
  - speaker: role-based label, e.g. "NV_CHINH", "NV_PHU", "ME", "NARRATOR"
  - speaker_gender: "male" | "female" | "neutral"

These fields are then used by Step 5 (TTS) to pick the correct voice ID.
"""
import json
import re
import requests
import config
from src.utils import setup_logging

logger = setup_logging("speaker_detector")

# Maximum segments to include in the LLM prompt.
# For very long videos we send the first N to keep token cost low.
_MAX_SEGMENTS_IN_PROMPT = 120


def _build_speaker_prompt(segments: list[dict]) -> str:
    """Build a compact prompt for the LLM to identify speakers."""
    # Only send id + original text (+ vi text for context).
    # We deliberately keep this compact to stay within token limits.
    sample = segments[:_MAX_SEGMENTS_IN_PROMPT]
    lines = []
    for s in sample:
        text_vi = s.get("text_vi", "")
        text_src = s.get("text", "")
        lines.append({"id": s["id"], "text": text_src, "text_vi": text_vi})

    data_json = json.dumps(lines, ensure_ascii=False, indent=2)

    return f"""You are analyzing a dialogue transcript to identify distinct speakers/characters.

TASK: For each segment assign:
1. "speaker" — a consistent role-based label in UPPERCASE_SNAKE_CASE.
   Rules:
   - Use role names, not real names. E.g.: NARRATOR, NV_CHINH (main character), NV_PHU (supporting), ME (mother), VO_CHONG (husband), VO (wife), CON (child), etc.
   - Dialogue lines that clearly belong to the same character MUST share the same speaker label across the entire transcript.
   - Narration / inner monologue / voiceover that has no visible speaker → "NARRATOR"
   - If only 1 person speaks throughout, use "NV_CHINH".

2. "gender" — "male", "female", or "neutral" (for NARRATOR when gender is unclear).
   Determine gender from pronouns, social roles, or context clues in both the source and Vietnamese text.

STRICT OUTPUT FORMAT — respond ONLY with valid JSON, no markdown:
{{
  "speakers": [
    {{"id": 1, "speaker": "NV_CHINH", "gender": "male"}},
    {{"id": 2, "speaker": "ME", "gender": "female"}}
  ]
}}

Transcript segments:
{data_json}
"""


def _parse_llm_response(text: str) -> list[dict] | None:
    """Extract and parse the JSON from the LLM response."""
    cleaned = text.strip()
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        return data.get("speakers")
    except Exception as e:
        logger.warning(f"Failed to parse speaker detection response: {e}")
        logger.debug(f"Raw response: {text[:300]}")
        return None


def _detect_via_gemini(prompt: str) -> list[dict] | None:
    """Call Gemini 2.0 Flash to detect speakers."""
    from src.utils import call_gemini_api
    res_text = call_gemini_api(prompt, temperature=0.1)
    if res_text:
        return _parse_llm_response(res_text)
    return None


def _detect_via_groq(prompt: str) -> list[dict] | None:
    """Call Groq Llama 3.3 70B to detect speakers."""
    from src.utils import call_groq_api
    res_text = call_groq_api(prompt, temperature=0.1)
    if res_text:
        return _parse_llm_response(res_text)
    return None


def detect_speakers(segments: list[dict]) -> list[dict]:
    """Detect speakers for each segment and add 'speaker' and 'speaker_gender' fields.

    Uses LLM (Gemini → Groq fallback) to analyze the transcript text and
    assign consistent speaker labels based on dialogue content and context.

    For segments beyond _MAX_SEGMENTS_IN_PROMPT, the last detected speakers
    are used as a "carry-forward" best guess (most videos have stable casts).

    Args:
        segments: List of segment dicts with at least 'id', 'text', 'text_vi'.

    Returns:
        Same list with 'speaker' and 'speaker_gender' added to each dict.
    """
    if not segments:
        return segments

    logger.info(f"Detecting speakers for {len(segments)} segments...")

    prompt = _build_speaker_prompt(segments)

    # Try Gemini first, then Groq
    speaker_list = _detect_via_gemini(prompt)
    if not speaker_list:
        logger.info("Gemini unavailable. Trying Groq...")
        speaker_list = _detect_via_groq(prompt)

    if not speaker_list:
        logger.warning(
            "Speaker detection failed from both Gemini and Groq. "
            "Falling back to config-based default voice for all segments."
        )
        # Fallback: apply default gender from config (or neutral)
        default_gender = getattr(config, "VOICE_TYPE", "male") or "male"
        return [
            {**s, "speaker": "NV_CHINH", "speaker_gender": default_gender}
            for s in segments
        ]

    # Build a lookup: id -> {speaker, gender}
    speaker_map: dict[int, dict] = {
        item["id"]: {"speaker": item.get("speaker", "NV_CHINH"), "gender": item.get("gender", "male")}
        for item in speaker_list
    }

    # Log the cast
    cast: dict[str, str] = {}
    for item in speaker_list:
        sp = item.get("speaker", "?")
        gn = item.get("gender", "?")
        if sp not in cast:
            cast[sp] = gn
    logger.info(f"Detected cast ({len(cast)} roles): " + ", ".join(f"{k}({v})" for k, v in cast.items()))

    # Apply to all segments; carry-forward for out-of-range ids
    last_info = {"speaker": "NV_CHINH", "gender": "male"}
    updated = []
    for s in segments:
        info = speaker_map.get(s["id"])
        if info:
            last_info = info
        else:
            # Beyond the sample window — reuse the last known speaker
            info = last_info
        updated.append({
            **s,
            "speaker": info["speaker"],
            "speaker_gender": info["gender"],
        })

    logger.info(f"Speaker detection complete: {len(cast)} distinct roles identified.")
    return updated


def get_voice_id_for_segment(seg: dict, voice_id_default: str, voice_map: dict | None = None) -> str:
    """Return the appropriate LucyLab voice ID for a segment based on speaker and gender.

    Priority:
      1. Map speaker label in voice_map (custom passed at runtime)
      2. Map speaker label in config.VOICE_CHARACTER_MAP
      3. Fallback for NARRATOR to config.VOICE_NARRATOR
      4. Fallback based on gender:
         - "female" -> config.VIETNAMESE_VOICEID_FEMALE
         - "male" -> config.VIETNAMESE_VOICEID_MALE
      5. Fallback to voice_id_default

    Args:
        seg: A segment dict, possibly containing 'speaker' and 'speaker_gender'.
        voice_id_default: The voice ID chosen by the user at pipeline start
                          (used as ultimate fallback).
        voice_map: Optional dictionary of speaker-to-voice mapping passed at runtime.

    Returns:
        A LucyLab voice ID string.
    """
    speaker = seg.get("speaker", "").strip().upper()
    gender = seg.get("speaker_gender", "")

    # 1. Check custom runtime voice map
    if voice_map and speaker in voice_map:
        return voice_map[speaker]

    # 2. Check config.VOICE_CHARACTER_MAP
    if hasattr(config, "VOICE_CHARACTER_MAP") and config.VOICE_CHARACTER_MAP and speaker in config.VOICE_CHARACTER_MAP:
        return config.VOICE_CHARACTER_MAP[speaker]

    # 3. Fallback for NARRATOR
    if speaker == "NARRATOR" and hasattr(config, "VOICE_NARRATOR") and config.VOICE_NARRATOR:
        return config.VOICE_NARRATOR

    # 4. Fallback based on gender
    if gender == "female":
        vid = getattr(config, "VIETNAMESE_VOICEID_FEMALE", "") or voice_id_default
        if vid:
            return vid
    elif gender == "male":
        vid = getattr(config, "VIETNAMESE_VOICEID_MALE", "") or voice_id_default
        if vid:
            return vid

    # 5. Ultimate fallback
    return voice_id_default
