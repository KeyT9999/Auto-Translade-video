import requests

import config
from src.ai.deepseek_provider import DeepSeekProvider


class DummyResponse:
    def __init__(self, status_code, json_data, headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._json_data


def test_deepseek_uses_split_timeouts_and_exponential_backoff(monkeypatch):
    provider = DeepSeekProvider()

    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(config, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(config, "DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr(config, "DEEPSEEK_CONNECT_TIMEOUT_MS", 15000)
    monkeypatch.setattr(config, "DEEPSEEK_READ_TIMEOUT_MS", 180000)
    monkeypatch.setattr(config, "DEEPSEEK_TIMEOUT_MS", 180000)
    monkeypatch.setattr(config, "DEEPSEEK_MAX_RETRIES", 5)
    monkeypatch.setattr(config, "DEEPSEEK_MIN_DELAY_MS", 5000)
    monkeypatch.setattr(config, "DEEPSEEK_MAX_DELAY_MS", 60000)
    monkeypatch.setattr(config, "DEEPSEEK_BACKOFF_MULTIPLIER", 2.0)
    monkeypatch.setattr(config, "DEEPSEEK_BACKOFF_JITTER", False)

    timeouts = []
    sleeps = []
    attempts = {"count": 0}

    def mock_post(url, headers, json, timeout):
        timeouts.append(timeout)
        attempts["count"] += 1
        if attempts["count"] < 5:
            raise requests.ReadTimeout("Read timed out")
        return DummyResponse(
            200,
            {"choices": [{"message": {"content": "ok"}}]},
        )

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr("src.ai.deepseek_provider.time.sleep", lambda seconds: sleeps.append(seconds))

    result = provider.generate_text("hello", request_label="window 0001_0020")

    assert result == "ok"
    assert timeouts == [(15.0, 180.0)] * 5
    assert sleeps == [5.0, 10.0, 20.0, 40.0]


def test_deepseek_retry_after_header_overrides_backoff(monkeypatch):
    provider = DeepSeekProvider()

    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(config, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(config, "DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr(config, "DEEPSEEK_CONNECT_TIMEOUT_MS", 15000)
    monkeypatch.setattr(config, "DEEPSEEK_READ_TIMEOUT_MS", 180000)
    monkeypatch.setattr(config, "DEEPSEEK_TIMEOUT_MS", 180000)
    monkeypatch.setattr(config, "DEEPSEEK_MAX_RETRIES", 2)
    monkeypatch.setattr(config, "DEEPSEEK_MIN_DELAY_MS", 5000)
    monkeypatch.setattr(config, "DEEPSEEK_MAX_DELAY_MS", 60000)
    monkeypatch.setattr(config, "DEEPSEEK_BACKOFF_MULTIPLIER", 2.0)
    monkeypatch.setattr(config, "DEEPSEEK_BACKOFF_JITTER", False)

    sleeps = []
    attempts = {"count": 0}

    def mock_post(url, headers, json, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return DummyResponse(429, {}, headers={"Retry-After": "7"})
        return DummyResponse(
            200,
            {"choices": [{"message": {"content": "ok"}}]},
        )

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr("src.ai.deepseek_provider.time.sleep", lambda seconds: sleeps.append(seconds))

    result = provider.generate_text("hello")

    assert result == "ok"
    assert sleeps == [7.0]
