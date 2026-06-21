import pytest
import requests
import config
from src.ai.openai_provider import OpenAIProvider

def test_openai_provider_fences():
    p = OpenAIProvider()
    assert p._strip_markdown_fences("```json\n{\"test\": 1}\n```") == '{"test": 1}'

def test_openai_provider_api(monkeypatch):
    p = OpenAIProvider()
    monkeypatch.setattr(config, "OPENAI_API_KEY", "mock-key")
    monkeypatch.setattr(config, "OPENAI_REPAIR_MODEL", "gpt-4o-mini")

    class DummyResponse:
        def __init__(self):
            self.status_code = 200
            self.headers = {}
        def raise_for_status(self):
            pass
        def json(self):
            return {
                "choices": [{
                    "message": {
                        "content": '{"repaired_segments": []}'
                    }
                }]
            }

    monkeypatch.setattr(requests, "post", lambda *a, **k: DummyResponse())
    res = p.generate_json("fix this please")
    assert res == {"repaired_segments": []}
