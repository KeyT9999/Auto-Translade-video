from src.ai.base import TextAIProvider, ASRProvider
from src.utils import call_groq_api

class GroqProvider(TextAIProvider, ASRProvider):
    def generate_text(self, prompt: str, temperature: float = 0.2, **kwargs) -> str:
        res = call_groq_api(prompt, temperature, response_json=False)
        if res is None:
            raise RuntimeError("Groq API text generation failed.")
        return res

    def generate_json(self, prompt: str, temperature: float = 0.2, **kwargs) -> dict:
        res = call_groq_api(prompt, temperature, response_json=True)
        if res is None:
            raise RuntimeError("Groq API JSON generation failed.")
        return self._safe_parse_json(res)

    def transcribe(self, audio_path: str, language: str | None = None) -> list[dict]:
        from src.transcriber import transcribe_groq
        res = transcribe_groq(audio_path, language)
        if res is None:
            raise RuntimeError("Groq ASR transcription failed.")
        return res
