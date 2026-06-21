import os
import sys
from dotenv import load_dotenv

load_dotenv()

def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        print(f"ERROR: Required environment variable '{key}' is not set.", file=sys.stderr)
        print(f"Please copy .env.example to .env and fill in your API keys.", file=sys.stderr)
        sys.exit(1)
    return value

# Azure Speech (fallback ASR — optional if using Groq as primary)
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "")

# Optional with defaults
TTS_VOICE = os.getenv("TTS_VOICE", "ja-JP-KeitaNeural")
TTS_MAX_SPEED_RATIO = float(os.getenv("TTS_MAX_SPEED_RATIO", "1.3"))
DEFAULT_SOURCE_LANG = os.getenv("DEFAULT_SOURCE_LANG", "en-US")
AUDIO_SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
# TTS Provider selection ('lucylab' or 'larvoice')
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "lucylab").strip().lower()

# LarVoice configuration
LARVOICE_API_KEY = os.getenv("LARVOICE_API_KEY", "")
LARVOICE_API_URL = os.getenv("LARVOICE_API_URL", "https://larvoice.com/api/v1/tts")
LARVOICE_VOICEID_MALE = os.getenv("LARVOICE_VOICEID_MALE", "1")
LARVOICE_VOICEID_FEMALE = os.getenv("LARVOICE_VOICEID_FEMALE", "39")

# Route default voice IDs and API key based on active provider
if TTS_PROVIDER == "larvoice":
    VIETNAMESE_API_KEY = os.getenv("LARVOICE_API_KEY", "")
    VIETNAMESE_VOICEID_MALE = os.getenv("LARVOICE_VOICEID_MALE", "1")
    VIETNAMESE_VOICEID_FEMALE = os.getenv("LARVOICE_VOICEID_FEMALE", "39")
    VOICE_NARRATOR = os.getenv("VOICE_NARRATOR", "1").strip()
else:
    # Default to LucyLab
    VIETNAMESE_API_KEY = os.getenv("VIETNAMESE_API_KEY", "")
    VIETNAMESE_VOICEID_MALE = os.getenv("VIETNAMESE_VOICEID_MALE", "")
    VIETNAMESE_VOICEID_FEMALE = os.getenv("VIETNAMESE_VOICEID_FEMALE", "")
    VOICE_NARRATOR = os.getenv("VOICE_NARRATOR", "").strip()

# Map character name (UPPERCASE) to voice ID. Format in .env: CHAR1:id1,CHAR2:id2
VOICE_CHARACTER_MAP = {}
_char_map_str = os.getenv("VOICE_CHARACTER_MAP", "")
if _char_map_str:
    for _item in _char_map_str.split(","):
        if ":" in _item:
            _k, _v = _item.split(":", 1)
            VOICE_CHARACTER_MAP[_k.strip().upper()] = _v.strip()
LUCYLAB_API_URL = os.getenv("LUCYLAB_API_URL", "https://api.lucylab.io/json-rpc")
VIETNAMESE_TTS_MAX_SPEED = float(os.getenv("VIETNAMESE_TTS_MAX_SPEED", "1.3"))
# Slow down factor for Vietnamese audio (0.82 = 18% slower, 1.0 = no change)
AUDIO_SLOW_FACTOR = float(os.getenv("AUDIO_SLOW_FACTOR", "0.82"))
# Audio loudness normalization (applied after merging TTS + background)
AUDIO_TARGET_LUFS = float(os.getenv("AUDIO_TARGET_LUFS", "-15.0"))
AUDIO_TRUE_PEAK = float(os.getenv("AUDIO_TRUE_PEAK", "-1.0"))
VIETNAMESE_OUTPUT_DIR = os.getenv("VIETNAMESE_OUTPUT_DIR", "")
VOICE_TYPE = os.getenv("VOICE_TYPE", os.getenv("Voice_type", "")).strip().lower()

VIETNAMESE_VIDEO_URL = os.getenv("VIETNAMESE_VIDEO_URL", os.getenv("Vietnamese_video_url", ""))

VIDEO_URL = os.getenv("VIDEO_URL", "")

# Google Gemini API (thumbnails + content generation)
GOOGLE_API_KEY = os.getenv("google_api_key", os.getenv("GOOGLE_API_KEY", ""))
IMAGE_MODEL_ID = os.getenv("image_model_id", "gemini-2.0-flash-exp")
CONTENT_MODEL_ID = os.getenv("content_model_id", "gemini-2.0-flash")

# Groq API (ASR Whisper & LLM Llama fallback)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Vivibe API (can fall back to LucyLab config)
VIVIBE_API_KEY = os.getenv("VIVIBE_API_KEY", VIETNAMESE_API_KEY)
VIVIBE_API_URL = os.getenv("VIVIBE_API_URL", LUCYLAB_API_URL)

# Publishing configurations
YOUTUBE_CLIENT_SECRETS = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")
YOUTUBE_TOKEN_PATH = os.getenv("YOUTUBE_TOKEN_PATH", "youtube_token.json")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
# Dynamic rate limit / API failure trackers
GEMINI_FAILED = False
GROQ_FAILED = False

# ── AI Provider Refactoring Config ──
ASR_PROVIDER = os.getenv("ASR_PROVIDER", "groq").strip().lower()
TRANSLATION_PROVIDER = os.getenv("TRANSLATION_PROVIDER", "deepseek").strip().lower()
QA_REPAIR_PROVIDER = os.getenv("QA_REPAIR_PROVIDER", "openai").strip().lower()

_fallback_trans = os.getenv("TRANSLATION_FALLBACK_PROVIDERS", "openai,groq")
TRANSLATION_FALLBACK_PROVIDERS = [x.strip().lower() for x in _fallback_trans.split(",") if x.strip()]

_fallback_qa = os.getenv("QA_REPAIR_FALLBACK_PROVIDERS", "deepseek,groq")
QA_REPAIR_FALLBACK_PROVIDERS = [x.strip().lower() for x in _fallback_qa.split(",") if x.strip()]

def _get_bool_env(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")

GEMINI_ENABLED = _get_bool_env("GEMINI_ENABLED", False)

# Groq ASR
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()
GROQ_ASR_MODEL = os.getenv("GROQ_ASR_MODEL", "whisper-large-v3").strip()
GROQ_ASR_LANGUAGE_AUTO = _get_bool_env("GROQ_ASR_LANGUAGE_AUTO", False)

# DeepSeek Translation
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip()
DEEPSEEK_TIMEOUT_MS = int(os.getenv("DEEPSEEK_TIMEOUT_MS", "60000"))
DEEPSEEK_MAX_RETRIES = int(os.getenv("DEEPSEEK_MAX_RETRIES", "5"))
DEEPSEEK_MIN_DELAY_MS = int(os.getenv("DEEPSEEK_MIN_DELAY_MS", "1500"))

# OpenAI QA / Repair
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
OPENAI_REPAIR_MODEL = os.getenv("OPENAI_REPAIR_MODEL", "gpt-4o-mini").strip()
OPENAI_TIMEOUT_MS = int(os.getenv("OPENAI_TIMEOUT_MS", "60000"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "5"))

# Translation Pipeline Controls
TRANSLATION_WINDOW_SIZE = int(os.getenv("TRANSLATION_WINDOW_SIZE", "35"))
TRANSLATION_CONTEXT_BEFORE = int(os.getenv("TRANSLATION_CONTEXT_BEFORE", "3"))
TRANSLATION_CONTEXT_AFTER = int(os.getenv("TRANSLATION_CONTEXT_AFTER", "3"))
TRANSLATION_CACHE_ENABLED = _get_bool_env("TRANSLATION_CACHE_ENABLED", True)
TRANSLATION_PARTIAL_SAVE_ENABLED = _get_bool_env("TRANSLATION_PARTIAL_SAVE_ENABLED", True)
TRANSLATION_FAIL_ON_CJK = _get_bool_env("TRANSLATION_FAIL_ON_CJK", True)
TRANSLATION_FAIL_ON_UNTRANSLATED_TEXT = _get_bool_env("TRANSLATION_FAIL_ON_UNTRANSLATED_TEXT", True)
TRANSLATION_MAX_REPAIR_ROUNDS = int(os.getenv("TRANSLATION_MAX_REPAIR_ROUNDS", "2"))

SUBTITLE_ONLY_TIMING_OVERFLOW_IS_WARNING = _get_bool_env("SUBTITLE_ONLY_TIMING_OVERFLOW_IS_WARNING", True)
VALIDATOR_HALLUCINATION_ENABLED = _get_bool_env("VALIDATOR_HALLUCINATION_ENABLED", True)
VALIDATOR_HALLUCINATION_SOURCE_CHAR_RATIO = float(os.getenv("VALIDATOR_HALLUCINATION_SOURCE_CHAR_RATIO", "2.5"))
VALIDATOR_ZH_VI_LENGTH_RATIO_AS_ERROR = _get_bool_env("VALIDATOR_ZH_VI_LENGTH_RATIO_AS_ERROR", False)
VALIDATOR_ZH_VI_LENGTH_RATIO_WARNING_THRESHOLD = float(os.getenv("VALIDATOR_ZH_VI_LENGTH_RATIO_WARNING_THRESHOLD", "5.0"))
VALIDATOR_ZH_VI_LENGTH_RATIO_ERROR_THRESHOLD = float(os.getenv("VALIDATOR_ZH_VI_LENGTH_RATIO_ERROR_THRESHOLD", "8.0"))
VALIDATOR_SUBTITLE_MAX_CHARS_PER_SECOND = float(os.getenv("VALIDATOR_SUBTITLE_MAX_CHARS_PER_SECOND", "22"))
VALIDATOR_SUBTITLE_HARD_MAX_CHARS_PER_SECOND = float(os.getenv("VALIDATOR_SUBTITLE_HARD_MAX_CHARS_PER_SECOND", "32"))

def validate_api_keys():
    """Validates that required API keys are set for active providers."""
    # ASR Provider
    if ASR_PROVIDER == "groq" and not GROQ_API_KEY:
        raise ValueError("ASR_PROVIDER is set to 'groq' but GROQ_API_KEY is not set.")
    # Translation Provider
    if TRANSLATION_PROVIDER == "deepseek" and not DEEPSEEK_API_KEY:
        raise ValueError("TRANSLATION_PROVIDER is set to 'deepseek' but DEEPSEEK_API_KEY is not set.")
    elif TRANSLATION_PROVIDER == "openai" and not OPENAI_API_KEY:
        raise ValueError("TRANSLATION_PROVIDER is set to 'openai' but OPENAI_API_KEY is not set.")
    elif TRANSLATION_PROVIDER == "gemini" and GEMINI_ENABLED and not GOOGLE_API_KEY:
        raise ValueError("TRANSLATION_PROVIDER is set to 'gemini' but GOOGLE_API_KEY is not set.")
    
    # QA Repair Provider
    if QA_REPAIR_PROVIDER == "openai" and not OPENAI_API_KEY:
        raise ValueError("QA_REPAIR_PROVIDER is set to 'openai' but OPENAI_API_KEY is not set.")
    elif QA_REPAIR_PROVIDER == "deepseek" and not DEEPSEEK_API_KEY:
        raise ValueError("QA_REPAIR_PROVIDER is set to 'deepseek' but DEEPSEEK_API_KEY is not set.")
    elif QA_REPAIR_PROVIDER == "gemini" and GEMINI_ENABLED and not GOOGLE_API_KEY:
        raise ValueError("QA_REPAIR_PROVIDER is set to 'gemini' but GOOGLE_API_KEY is not set.")

# ── Subtitle Cover & ASS Renderer Config ──
SUBTITLE_MASK_Y_PERCENT = float(os.getenv("SUBTITLE_MASK_Y_PERCENT", "0.82"))
SUBTITLE_MASK_HEIGHT_PERCENT = float(os.getenv("SUBTITLE_MASK_HEIGHT_PERCENT", "0.18"))
SUBTITLE_MASK_OPACITY = float(os.getenv("SUBTITLE_MASK_OPACITY", "0.55"))
SUBTITLE_FONT_NAME = os.getenv("SUBTITLE_FONT_NAME", "Arial")
SUBTITLE_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", "48"))
SUBTITLE_OUTLINE_SIZE = int(os.getenv("SUBTITLE_OUTLINE_SIZE", "2"))
SUBTITLE_SHADOW_SIZE = int(os.getenv("SUBTITLE_SHADOW_SIZE", "1"))
SUBTITLE_BOX_OPACITY = float(os.getenv("SUBTITLE_BOX_OPACITY", "0.6"))
SUBTITLE_MARGIN_BOTTOM = int(os.getenv("SUBTITLE_MARGIN_BOTTOM", "60"))
SUBTITLE_MAX_CHARS_PER_LINE = int(os.getenv("SUBTITLE_MAX_CHARS_PER_LINE", "24"))

