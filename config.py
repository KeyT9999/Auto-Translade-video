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
# Vietnamese TTS (LucyLab API)
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
FACEBOOK_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN", "")
