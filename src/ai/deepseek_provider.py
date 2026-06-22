import logging
import random
import time

import requests

import config
from src.ai.base import TextAIProvider

logger = logging.getLogger("deepseek_provider")


class DeepSeekProvider(TextAIProvider):
    RETRYABLE_STATUS_CODES = {429, 502, 503, 504}

    def __init__(self):
        super().__init__()

    def _build_timeout(self) -> tuple[float, float]:
        connect_timeout = max(config.DEEPSEEK_CONNECT_TIMEOUT_MS, 1) / 1000.0
        read_timeout_ms = max(config.DEEPSEEK_READ_TIMEOUT_MS, config.DEEPSEEK_TIMEOUT_MS, 1)
        read_timeout = read_timeout_ms / 1000.0
        return connect_timeout, read_timeout

    def _compute_retry_delay(
        self,
        attempt: int,
        response: requests.Response | None = None,
    ) -> float:
        min_delay = max(config.DEEPSEEK_MIN_DELAY_MS, 0) / 1000.0
        max_delay = max(config.DEEPSEEK_MAX_DELAY_MS, config.DEEPSEEK_MIN_DELAY_MS, 1) / 1000.0

        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(max(float(retry_after), 0.0), max_delay)
                except ValueError:
                    pass

        multiplier = max(config.DEEPSEEK_BACKOFF_MULTIPLIER, 1.0)
        delay = min_delay * (multiplier ** max(attempt - 1, 0))
        delay = min(delay, max_delay)

        if config.DEEPSEEK_BACKOFF_JITTER and delay > 0:
            jitter_window = min(delay * 0.2, 3.0)
            delay = min(max_delay, max(0.0, delay + random.uniform(-jitter_window, jitter_window)))

        return delay

    def _build_retryable_http_error(self, response: requests.Response) -> requests.HTTPError:
        return requests.HTTPError(
            f"DeepSeek returned retryable status {response.status_code}",
            response=response,
        )

    def _call_api_with_retry(
        self,
        prompt: str,
        temperature: float = 0.2,
        response_format: str = "text",
        request_label: str | None = None,
    ) -> str:
        api_key = config.DEEPSEEK_API_KEY
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set.")

        base_url = config.DEEPSEEK_BASE_URL.rstrip("/")
        url = f"{base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config.DEEPSEEK_MODEL,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }

        if response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}

        max_retries = max(config.DEEPSEEK_MAX_RETRIES, 1)
        timeout = self._build_timeout()
        label = f" ({request_label})" if request_label else ""

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Calling DeepSeek API%s: model=%s, attempt=%s/%s, timeout=(%.1fs connect, %.1fs read)",
                    label,
                    config.DEEPSEEK_MODEL,
                    attempt,
                    max_retries,
                    timeout[0],
                    timeout[1],
                )

                response = requests.post(url, headers=headers, json=payload, timeout=timeout)

                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    error = self._build_retryable_http_error(response)
                    if attempt == max_retries:
                        logger.error(
                            "DeepSeek API call failed after %s attempts%s: %s",
                            max_retries,
                            label,
                            error,
                        )
                        raise error

                    delay = self._compute_retry_delay(attempt, response=response)
                    logger.warning(
                        "DeepSeek API retryable status %s%s. Retrying in %.2f seconds...",
                        response.status_code,
                        label,
                        delay,
                    )
                    time.sleep(delay)
                    continue

                response.raise_for_status()
                result = response.json()

                choices = result.get("choices", [])
                if not choices:
                    raise ValueError(f"DeepSeek response choices list is empty: {result}")

                content = choices[0].get("message", {}).get("content", "")
                return content

            except requests.RequestException as exc:
                if attempt == max_retries:
                    logger.error(
                        "DeepSeek API call failed after %s attempts%s: %s",
                        max_retries,
                        label,
                        exc,
                    )
                    raise

                delay = self._compute_retry_delay(attempt)
                logger.warning(
                    "DeepSeek API request failed%s: %s. Retrying in %.2f seconds...",
                    label,
                    exc,
                    delay,
                )
                time.sleep(delay)

        raise RuntimeError("DeepSeek API call exceeded maximum retries without a successful response.")

    def generate_text(
        self,
        prompt: str,
        temperature: float = 0.2,
        request_label: str | None = None,
        **kwargs,
    ) -> str:
        return self._call_api_with_retry(
            prompt,
            temperature,
            response_format="text",
            request_label=request_label,
        )

    def generate_json(
        self,
        prompt: str,
        temperature: float = 0.2,
        request_label: str | None = None,
        **kwargs,
    ) -> dict:
        text_resp = self._call_api_with_retry(
            prompt,
            temperature,
            response_format="json_object",
            request_label=request_label,
        )
        return self._safe_parse_json(text_resp)
