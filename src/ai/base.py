from abc import ABC, abstractmethod
import json

class TextAIProvider(ABC):
    """Base class for LLM text generation providers."""
    
    @abstractmethod
    def generate_text(self, prompt: str, temperature: float = 0.2, **kwargs) -> str:
        """Generates raw text from a prompt."""
        pass

    @abstractmethod
    def generate_json(self, prompt: str, temperature: float = 0.2, **kwargs) -> dict:
        """Generates and parses a JSON response from a prompt."""
        pass

    def _strip_markdown_fences(self, text: str) -> str:
        """Utility to strip markdown code blocks like ```json ... ```."""
        text = text.strip()
        if text.startswith("```"):
            first_nl = text.find("\n")
            if first_nl != -1:
                text = text[first_nl:].strip()
            else:
                text = text[3:].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
        return text

    def _safe_parse_json(self, text: str) -> dict:
        """Safely parses JSON by stripping markdown fences first."""
        cleaned = self._strip_markdown_fences(text)
        # Handle simple cases of unescaped control chars if necessary, or just standard loads
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            # Try to fix some common json format errors (like trailing commas or single quotes)
            # but don't do too much magic; let the repair pipeline handle it.
            raise e

class ASRProvider(ABC):
    """Base class for speech-to-text providers."""
    
    @abstractmethod
    def transcribe(self, audio_path: str, language: str | None = None) -> list[dict]:
        """Transcribes audio file to segments list."""
        pass
