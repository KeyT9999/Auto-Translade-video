import pytest
from src.ai.openai_provider import OpenAIProvider
from src.ai.deepseek_provider import DeepSeekProvider
from src.ai.gemini_provider import GeminiProvider
from src.ai.groq_provider import GroqProvider

def test_instantiate_providers():
    openai = OpenAIProvider()
    deepseek = DeepSeekProvider()
    gemini = GeminiProvider()
    groq = GroqProvider()
    
    assert openai is not None
    assert deepseek is not None
    assert gemini is not None
    assert groq is not None
