import time
import logging
import requests
import json
import config
from src.ai.base import TextAIProvider

logger = logging.getLogger("deepseek_provider")

class DeepSeekProvider(TextAIProvider):
    def __init__(self):
        super().__init__()

    def _call_api_with_retry(self, prompt: str, temperature: float = 0.2, response_format: str = "text") -> str:
        api_key = config.DEEPSEEK_API_KEY
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set.")
            
        base_url = config.DEEPSEEK_BASE_URL.rstrip('/')
        url = f"{base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": config.DEEPSEEK_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }
        
        # DeepSeek and standard OpenAI endpoints support response_format for JSON
        if response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}

        max_retries = config.DEEPSEEK_MAX_RETRIES
        min_delay = config.DEEPSEEK_MIN_DELAY_MS / 1000.0  # convert to seconds
        timeout = config.DEEPSEEK_TIMEOUT_MS / 1000.0      # convert to seconds

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Calling DeepSeek API: model={config.DEEPSEEK_MODEL}, attempt={attempt}/{max_retries}")
                
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                
                # Check for rate limit or specific Retry-After
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            delay = min_delay * (2 ** (attempt - 1))
                    else:
                        delay = min_delay * (2 ** (attempt - 1))
                    logger.warning(f"DeepSeek rate limit 429. Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                    continue
                
                response.raise_for_status()
                result = response.json()
                
                choices = result.get("choices", [])
                if not choices:
                    raise ValueError(f"DeepSeek response choices list is empty: {result}")
                
                content = choices[0].get("message", {}).get("content", "")
                return content
                
            except requests.RequestException as e:
                delay = min_delay * (2 ** (attempt - 1))
                if attempt == max_retries:
                    logger.error(f"DeepSeek API call failed after {max_retries} attempts: {e}")
                    raise e
                logger.warning(f"DeepSeek API connection failed: {e}. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)

        raise RuntimeError("DeepSeek API call exceeded maximum retries without a successful response.")

    def generate_text(self, prompt: str, temperature: float = 0.2, **kwargs) -> str:
        return self._call_api_with_retry(prompt, temperature, response_format="text")

    def generate_json(self, prompt: str, temperature: float = 0.2, **kwargs) -> dict:
        text_resp = self._call_api_with_retry(prompt, temperature, response_format="json_object")
        return self._safe_parse_json(text_resp)
