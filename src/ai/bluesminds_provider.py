import time
import logging
import requests

import config
from src.ai.base import TextAIProvider

logger = logging.getLogger("bluesminds_provider")


class BluesMindsProvider(TextAIProvider):
    """BluesMinds AI provider — OpenAI-compatible endpoint at api.bluesminds.com.

    Designed to support multiple models from the unified gateway.
    When quota is exhausted (HTTP 429 or 403), the exception propagates so that
    the AIRouter's fallback chain can try the next provider.
    """

    RETRYABLE_STATUS_CODES = {502, 503, 504}

    def __init__(self):
        super().__init__()

    @staticmethod
    def _resolve_api_key() -> str:
        """Return the BluesMinds API key."""
        raw = config.BLUESMINDS_API_KEY
        if not raw:
            raise ValueError("BLUESMINDS_API_KEY is not set.")
        return raw

    def _call_api_with_retry(
        self,
        prompt: str,
        temperature: float = 0.2,
        response_format: str = "text",
    ) -> str:
        api_key = self._resolve_api_key()

        base_url = config.BLUESMINDS_BASE_URL.rstrip("/")
        # The endpoint expects /v1 suffix if not already present
        if not base_url.endswith("/v1"):
            url = f"{base_url}/v1/chat/completions"
        else:
            url = f"{base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config.BLUESMINDS_MODEL,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }

        if response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}

        max_retries = config.BLUESMINDS_MAX_RETRIES
        timeout = config.BLUESMINDS_TIMEOUT_MS / 1000.0
        min_delay = 1.0

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Calling BluesMinds API: model=%s, attempt=%s/%s",
                    config.BLUESMINDS_MODEL,
                    attempt,
                    max_retries,
                )

                response = requests.post(
                    url, headers=headers, json=payload, timeout=timeout
                )

                # ── Quota exhaustion / Permission issues — bubble up immediately ──
                if response.status_code in (429, 403, 401):
                    body = ""
                    try:
                        body = response.text[:200]
                    except Exception:
                        pass
                    raise requests.HTTPError(
                        f"BluesMinds error ({response.status_code}): {body}",
                        response=response,
                    )

                # ── Retryable server errors ──
                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    delay = min_delay * (2 ** (attempt - 1))
                    if attempt == max_retries:
                        logger.error(
                            "BluesMinds API failed after %s attempts: HTTP %s",
                            max_retries,
                            response.status_code,
                        )
                        response.raise_for_status()
                    logger.warning(
                        "BluesMinds API server error %s. Retrying in %.2f seconds...",
                        response.status_code,
                        delay,
                    )
                    time.sleep(delay)
                    continue

                response.raise_for_status()
                result = response.json()

                choices = result.get("choices", [])
                if not choices:
                    raise ValueError(
                        f"BluesMinds response choices list is empty: {result}"
                    )

                content = choices[0].get("message", {}).get("content", "")
                return content

            except requests.HTTPError:
                # Let HTTPError (quota, auth) propagate without retry
                raise
            except requests.RequestException as e:
                delay = min_delay * (2 ** (attempt - 1))
                if attempt == max_retries:
                    logger.error(
                        "BluesMinds API call failed after %s attempts: %s",
                        max_retries,
                        e,
                    )
                    raise
                logger.warning(
                    "BluesMinds API connection failed: %s. Retrying in %.2f seconds...",
                    e,
                    delay,
                )
                time.sleep(delay)

        raise RuntimeError(
            "BluesMinds API call exceeded maximum retries without a successful response."
        )

    def generate_text(self, prompt: str, temperature: float = 0.2, **kwargs) -> str:
        return self._call_api_with_retry(prompt, temperature, response_format="text")

    def generate_json(self, prompt: str, temperature: float = 0.2, **kwargs) -> dict:
        text_resp = self._call_api_with_retry(
            prompt, temperature, response_format="json_object"
        )
        return self._safe_parse_json(text_resp)
