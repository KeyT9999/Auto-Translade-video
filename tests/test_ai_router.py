import pytest
import config
from src.ai.router import AIRouter

def test_router_routing_and_fallback(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "deepseek")
    monkeypatch.setenv("TRANSLATION_FALLBACK_PROVIDERS", "openai,groq")
    monkeypatch.setenv("GEMINI_ENABLED", "false")

    import importlib
    importlib.reload(config)

    router = AIRouter()
    
    # Mock deepseek
    deepseek = router.get_provider("deepseek")
    monkeypatch.setattr(deepseek, "generate_json", lambda prompt, *a, **kw: {"deepseek_json": prompt})

    res = router.translate("hello")
    assert res == {"deepseek_json": "hello"}

def test_router_fallback_trigger(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "deepseek")
    monkeypatch.setenv("TRANSLATION_FALLBACK_PROVIDERS", "openai")
    monkeypatch.setenv("GEMINI_ENABLED", "false")

    import importlib
    importlib.reload(config)

    router = AIRouter()

    # Mock DeepSeek to fail to trigger fallback
    deepseek = router.get_provider("deepseek")
    def fail_gen(*args, **kwargs):
        raise ValueError("DeepSeek is overloaded!")
    monkeypatch.setattr(deepseek, "generate_json", fail_gen)

    # Mock OpenAI
    openai = router.get_provider("openai")
    monkeypatch.setattr(openai, "generate_json", lambda prompt, *a, **kw: {"openai_json": prompt})

    res = router.translate("hello")
    assert res == {"openai_json": "hello"}

def test_router_gemini_disabled(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "gemini")
    monkeypatch.setenv("TRANSLATION_FALLBACK_PROVIDERS", "openai")
    monkeypatch.setenv("GEMINI_ENABLED", "false")

    import importlib
    importlib.reload(config)

    router = AIRouter()

    # Mock Gemini (should not be called, but let's mock it just in case it is called incorrectly to raise error)
    gemini = router.get_provider("gemini")
    monkeypatch.setattr(gemini, "generate_json", lambda prompt, *a, **kw: {"gemini_json": prompt})

    # Mock OpenAI
    openai = router.get_provider("openai")
    monkeypatch.setattr(openai, "generate_json", lambda prompt, *a, **kw: {"openai_json": prompt})

    res = router.translate("hello")
    assert res == {"openai_json": "hello"}


def test_router_blacklist_on_failure(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "deepseek")
    monkeypatch.setenv("TRANSLATION_FALLBACK_PROVIDERS", "openai")
    monkeypatch.setenv("GEMINI_ENABLED", "false")

    import importlib
    importlib.reload(config)

    router = AIRouter()

    # Mock DeepSeek to fail on first call
    deepseek = router.get_provider("deepseek")
    call_count = 0
    def fail_gen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise ValueError("DeepSeek is overloaded!")
    monkeypatch.setattr(deepseek, "generate_json", fail_gen)

    # Mock OpenAI
    openai = router.get_provider("openai")
    monkeypatch.setattr(openai, "generate_json", lambda prompt, *a, **kw: {"openai_json": prompt})

    # First call fails on DeepSeek, falls back to OpenAI
    res1 = router.translate("hello")
    assert res1 == {"openai_json": "hello"}
    assert call_count == 1

    # Second call should skip DeepSeek completely and go straight to OpenAI (because DeepSeek is blacklisted)
    res2 = router.translate("world")
    assert res2 == {"openai_json": "world"}
    assert call_count == 1  # call_count remains 1, meaning DeepSeek was not called again!

    # Test reset_failures()
    router.reset_failures()
    res3 = router.translate("reset")
    assert res3 == {"openai_json": "reset"}
    assert call_count == 2  # call_count becomes 2, meaning DeepSeek was tried again!

