import pytest
from src.ai.openai_provider import OpenAIProvider
from src.ai.deepseek_provider import DeepSeekProvider
from src.ai.gemini_provider import GeminiProvider
from src.ai.groq_provider import GroqProvider
from src.ai.evomap_provider import EvoMapProvider
from src.ai.bluesminds_provider import BluesMindsProvider

def test_instantiate_providers():
    openai = OpenAIProvider()
    deepseek = DeepSeekProvider()
    gemini = GeminiProvider()
    groq = GroqProvider()
    evomap = EvoMapProvider()
    bluesminds = BluesMindsProvider()
    
    assert openai is not None
    assert deepseek is not None
    assert gemini is not None
    assert groq is not None
    assert evomap is not None
    assert bluesminds is not None
