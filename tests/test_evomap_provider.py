import pytest
import requests
import config
from src.ai.evomap_provider import EvoMapProvider


def test_evomap_provider_api_key_prefix():
    """Verify the auto-prefix logic for API keys."""
    p = EvoMapProvider()

    # Already prefixed key should stay unchanged
    original = "sk-evomap-abc123"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "EVOMAP_API_KEY", original)
        assert p._resolve_api_key() == original

    # Raw key gets prefixed
    raw = "abc123"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "EVOMAP_API_KEY", raw)
        assert p._resolve_api_key() == "sk-evomap-abc123"


def test_evomap_provider_api_key_missing():
    """Raise ValueError when EVOMAP_API_KEY is empty."""
    p = EvoMapProvider()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "EVOMAP_API_KEY", "")
        with pytest.raises(ValueError, match="EVOMAP_API_KEY is not set"):
            p._resolve_api_key()


def test_evomap_provider_success(monkeypatch):
    """Successful API call returns parsed JSON."""
    p = EvoMapProvider()
    monkeypatch.setattr(config, "EVOMAP_API_KEY", "test-key")
    monkeypatch.setattr(config, "EVOMAP_MODEL", "evomap-gemini-3.1-pro-preview")

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


def test_evomap_provider_429_raises_immediately(monkeypatch):
    """HTTP 429 should raise immediately without retrying, so the router can fallback."""
    p = EvoMapProvider()
    monkeypatch.setattr(config, "EVOMAP_API_KEY", "test-key")
    monkeypatch.setattr(config, "EVOMAP_MAX_RETRIES", 3)

    call_count = 0

    class Quota429Response:
        def __init__(self):
            self.status_code = 429
            self.headers = {}
            self.text = "quota exhausted"
        def raise_for_status(self):
            raise requests.HTTPError("429", response=self)

    def fake_post(*a, **k):
        nonlocal call_count
        call_count += 1
        return Quota429Response()

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(requests.HTTPError, match="429"):
        p.generate_text("hello")

    # Should only be called ONCE — no retry on 429
    assert call_count == 1


def test_evomap_provider_sends_correct_headers(monkeypatch):
    """Verify the request is sent with correct authorization and model."""
    p = EvoMapProvider()
    monkeypatch.setattr(config, "EVOMAP_API_KEY", "my-raw-key")
    monkeypatch.setattr(config, "EVOMAP_BASE_URL", "https://api.evomap.ai/v1")
    monkeypatch.setattr(config, "EVOMAP_MODEL", "evomap-gemini-3.1-pro-preview")

    captured = {}

    class DummyResponse:
        status_code = 200
        headers = {}
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def capture_post(url, headers=None, json=None, **k):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr(requests, "post", capture_post)
    p.generate_text("test prompt")

    assert captured["url"] == "https://api.evomap.ai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-evomap-my-raw-key"
    assert captured["json"]["model"] == "evomap-gemini-3.1-pro-preview"
