import pytest
import requests
import config
from src.ai.bluesminds_provider import BluesMindsProvider


def test_bluesminds_provider_api_key_missing():
    """Raise ValueError when BLUESMINDS_API_KEY is empty."""
    p = BluesMindsProvider()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "BLUESMINDS_API_KEY", "")
        with pytest.raises(ValueError, match="BLUESMINDS_API_KEY is not set"):
            p._resolve_api_key()


def test_bluesminds_provider_success(monkeypatch):
    """Successful API call returns parsed JSON/text."""
    p = BluesMindsProvider()
    monkeypatch.setattr(config, "BLUESMINDS_API_KEY", "test-key")
    monkeypatch.setattr(config, "BLUESMINDS_MODEL", "DeepSeek-V4-Flash")

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


def test_bluesminds_provider_429_raises_immediately(monkeypatch):
    """HTTP 429/403/401 should raise immediately without retrying, so the router can fallback."""
    p = BluesMindsProvider()
    monkeypatch.setattr(config, "BLUESMINDS_API_KEY", "test-key")
    monkeypatch.setattr(config, "BLUESMINDS_MAX_RETRIES", 3)

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

    # Should only be called ONCE — no retry on 429/403/401
    assert call_count == 1


def test_bluesminds_provider_sends_correct_headers(monkeypatch):
    """Verify the request is sent with correct authorization and model."""
    p = BluesMindsProvider()
    monkeypatch.setattr(config, "BLUESMINDS_API_KEY", "my-key")
    monkeypatch.setattr(config, "BLUESMINDS_BASE_URL", "https://api.bluesminds.com")
    monkeypatch.setattr(config, "BLUESMINDS_MODEL", "DeepSeek-V4-Flash")

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

    assert captured["url"] == "https://api.bluesminds.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer my-key"
    assert captured["json"]["model"] == "DeepSeek-V4-Flash"
