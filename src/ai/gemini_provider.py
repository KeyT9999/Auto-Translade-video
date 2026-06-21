import config
from src.ai.base import TextAIProvider
from src.utils import call_gemini_api

class GeminiProvider(TextAIProvider):
    def generate_text(self, prompt: str, temperature: float = 0.2, **kwargs) -> str:
        if not config.GEMINI_ENABLED:
            raise RuntimeError("Gemini is disabled by config.")
        res = call_gemini_api(prompt, temperature, response_mime_type="text/plain")
        if res is None:
            raise RuntimeError("Gemini API call failed.")
        return res

    def generate_json(self, prompt: str, temperature: float = 0.2, **kwargs) -> dict:
        if not config.GEMINI_ENABLED:
            raise RuntimeError("Gemini is disabled by config.")
        res = call_gemini_api(prompt, temperature, response_mime_type="application/json")
        if res is None:
            raise RuntimeError("Gemini API call failed.")
        return self._safe_parse_json(res)
