import logging
from typing import List, Dict, Any, Optional
import config
from src.ai.base import TextAIProvider, ASRProvider

logger = logging.getLogger("ai_router")

class AIRouter:
    def __init__(self):
        self._providers = {}
        self._asr_providers = {}
        self._initialized = False

    def _init_providers(self):
        if self._initialized:
            return
        
        # Dynamically import to avoid circular dependencies and allow incremental implementations
        try:
            from src.ai.openai_provider import OpenAIProvider
            self._providers["openai"] = OpenAIProvider()
        except ImportError:
            pass

        try:
            from src.ai.deepseek_provider import DeepSeekProvider
            self._providers["deepseek"] = DeepSeekProvider()
        except ImportError:
            pass

        try:
            from src.ai.gemini_provider import GeminiProvider
            self._providers["gemini"] = GeminiProvider()
        except ImportError:
            pass

        try:
            from src.ai.groq_provider import GroqProvider
            groq_p = GroqProvider()
            self._providers["groq"] = groq_p
            self._asr_providers["groq"] = groq_p
        except ImportError:
            pass
        
        self._initialized = True

    def get_provider(self, name: str) -> Optional[TextAIProvider]:
        self._init_providers()
        return self._providers.get(name.lower())

    def get_asr_provider(self, name: str) -> Optional[ASRProvider]:
        self._init_providers()
        return self._asr_providers.get(name.lower())

    def _execute_with_fallback(self, 
                               primary_name: str, 
                               fallback_names: List[str], 
                               stage: str, 
                               method_name: str, 
                               *args, 
                               **kwargs) -> Any:
        """Executes a method on primary provider, falling back to other providers in sequence if it fails."""
        providers_to_try = [primary_name] + fallback_names
        last_error = None

        for provider_name in providers_to_try:
            # Respect GEMINI_ENABLED
            if provider_name.lower() == "gemini" and not config.GEMINI_ENABLED:
                logger.info(f"Gemini disabled by config. Skipping Gemini for {stage}.")
                continue

            provider = self.get_provider(provider_name)
            if not provider:
                logger.warning(f"Provider '{provider_name}' not available for {stage}.")
                continue

            # Log stage initiation with provider and model info
            model_key = f"{provider_name.upper()}_MODEL"
            if provider_name.lower() == "openai" and stage == "repair":
                model_key = "OPENAI_REPAIR_MODEL"
            elif provider_name.lower() == "groq" and stage == "asr":
                model_key = "GROQ_ASR_MODEL"
            
            model_name = getattr(config, model_key, "unknown")
            logger.info(f"AI Stage [{stage}] using provider={provider_name}, model={model_name}")

            try:
                method = getattr(provider, method_name)
                return method(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Provider '{provider_name}' failed for stage '{stage}' via method '{method_name}': {e}")
                last_error = e

        if last_error:
            raise RuntimeError(f"All providers failed for stage '{stage}': {last_error}") from last_error
        else:
            raise ValueError(f"No active provider found for stage '{stage}' with requested providers {providers_to_try}")

    # Central routing APIs
    def generate_context(self, prompt: str, **kwargs) -> dict:
        return self._execute_with_fallback(
            primary_name=config.TRANSLATION_PROVIDER,
            fallback_names=config.TRANSLATION_FALLBACK_PROVIDERS,
            stage="context",
            method_name="generate_json",
            prompt=prompt,
            **kwargs
        )

    def generate_glossary(self, prompt: str, **kwargs) -> dict:
        return self._execute_with_fallback(
            primary_name=config.TRANSLATION_PROVIDER,
            fallback_names=config.TRANSLATION_FALLBACK_PROVIDERS,
            stage="glossary",
            method_name="generate_json",
            prompt=prompt,
            **kwargs
        )

    def generate_character_bible(self, prompt: str, **kwargs) -> dict:
        return self._execute_with_fallback(
            primary_name=config.TRANSLATION_PROVIDER,
            fallback_names=config.TRANSLATION_FALLBACK_PROVIDERS,
            stage="character",
            method_name="generate_json",
            prompt=prompt,
            **kwargs
        )

    def translate(self, prompt: str, **kwargs) -> dict:
        return self._execute_with_fallback(
            primary_name=config.TRANSLATION_PROVIDER,
            fallback_names=config.TRANSLATION_FALLBACK_PROVIDERS,
            stage="translation",
            method_name="generate_json",
            prompt=prompt,
            **kwargs
        )

    def repair(self, prompt: str, **kwargs) -> dict:
        return self._execute_with_fallback(
            primary_name=config.QA_REPAIR_PROVIDER,
            fallback_names=config.QA_REPAIR_FALLBACK_PROVIDERS,
            stage="repair",
            method_name="generate_json",
            prompt=prompt,
            **kwargs
        )

    def rewrite_timeline(self, prompt: str, **kwargs) -> dict:
        return self._execute_with_fallback(
            primary_name=config.QA_REPAIR_PROVIDER,
            fallback_names=config.QA_REPAIR_FALLBACK_PROVIDERS,
            stage="timeline_rewrite",
            method_name="generate_json",
            prompt=prompt,
            **kwargs
        )

    def detect_speakers(self, prompt: str, **kwargs) -> dict:
        return self._execute_with_fallback(
            primary_name=config.TRANSLATION_PROVIDER,
            fallback_names=config.TRANSLATION_FALLBACK_PROVIDERS,
            stage="speaker_detection",
            method_name="generate_json",
            prompt=prompt,
            **kwargs
        )

    def asr(self, audio_path: str, language: str | None = None) -> List[Dict[str, Any]]:
        primary_name = config.ASR_PROVIDER
        logger.info(f"AI Stage [asr] using provider={primary_name}, model={config.GROQ_ASR_MODEL}")
        asr_provider = self.get_asr_provider(primary_name)
        if asr_provider:
            try:
                return asr_provider.transcribe(audio_path, language)
            except Exception as e:
                logger.warning(f"ASR Provider '{primary_name}' failed: {e}")
                
        if config.AZURE_SPEECH_KEY and config.AZURE_SPEECH_REGION:
            raise RuntimeError(f"ASR provider {primary_name} failed. Triggering Azure Speech SDK fallback.")
        
        raise RuntimeError(f"ASR provider {primary_name} failed and no fallback available.")

ai_router = AIRouter()
