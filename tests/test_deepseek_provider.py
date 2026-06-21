import pytest
import json
import requests
from src.ai.deepseek_provider import DeepSeekProvider
import config

def test_strip_markdown_fences():
    p = DeepSeekProvider()
    
    raw = "```json\n{\n  \"hello\": \"world\"\n}\n```"
    assert p._strip_markdown_fences(raw) == '{\n  "hello": "world"\n}'

    raw2 = "```\n{\n  \"hello\": \"world\"\n}\n```"
    assert p._strip_markdown_fences(raw2) == '{\n  "hello": "world"\n}'

    raw3 = '{"hello": "world"}'
    assert p._strip_markdown_fences(raw3) == '{"hello": "world"}'

def test_safe_parse_json():
    p = DeepSeekProvider()
    raw = "```json\n{\n  \"hello\": \"world\"\n}\n```"
    assert p._safe_parse_json(raw) == {"hello": "world"}

    with pytest.raises(json.JSONDecodeError):
        p._safe_parse_json("{invalid_json}")

def test_deepseek_provider_success(monkeypatch):
    p = DeepSeekProvider()
    
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(config, "DEEPSEEK_MODEL", "deepseek-v4-flash")
    
    class DummyResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data
            self.headers = {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError("Error")

        def json(self):
            return self._json_data

    def mock_post(url, headers, json, timeout):
        return DummyResponse(200, {
            "choices": [{
                "message": {
                    "content": '{"success": true}'
                }
            }]
        })

    monkeypatch.setattr(requests, "post", mock_post)
    
    res = p.generate_json("test prompt")
    assert res == {"success": True}

def test_deepseek_provider_retry(monkeypatch):
    p = DeepSeekProvider()
    
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(config, "DEEPSEEK_MAX_RETRIES", 2)
    monkeypatch.setattr(config, "DEEPSEEK_MIN_DELAY_MS", 10)
    
    call_count = 0
    
    class DummyResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data
            self.headers = {}

        def raise_for_status(self):
            pass

        def json(self):
            return self._json_data

    def mock_post(url, headers, json, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Let's return a dummy response with status 429
            resp = DummyResponse(429, {})
            return resp
        return DummyResponse(200, {
            "choices": [{
                "message": {
                    "content": "successful after retry"
                }
            }]
        })

    monkeypatch.setattr(requests, "post", mock_post)
    
    res = p.generate_text("test prompt")
    assert res == "successful after retry"
    assert call_count == 2
