import os
import logging


def setup_logging(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(handler)
    return logger


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def extract_url(text: str) -> str:
    """Extracts the first HTTP/HTTPS URL from a string.
    
    If no URL is found, returns the stripped original text.
    """
    if not text:
        return ""
    import re
    match = re.search(r'(https?://[^\s]+)', text)
    if match:
        url = match.group(1).strip()
        url = re.sub(r'[.,;:!?"\'()\[\]{}“”‘’]+$', '', url)
        return url
    return text.strip()


def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def call_gemini_api(prompt: str, temperature: float = 0.2, response_mime_type: str = "application/json") -> str | None:
    import config
    import logging
    logger = logging.getLogger("api_helpers")
    
    if not getattr(config, "GEMINI_ENABLED", False):
        return None
    if getattr(config, "GEMINI_FAILED", False) or not config.GOOGLE_API_KEY:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=config.GOOGLE_API_KEY)
        response = client.models.generate_content(
            model=config.CONTENT_MODEL_ID or "gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type=response_mime_type,
            ),
        )
        if response.text:
            return response.text
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Gemini API call failed: {err_msg}")
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            config.GEMINI_FAILED = True
            logger.warning("Gemini rate limit reached (429 / RESOURCE_EXHAUSTED). Permanently switching to Groq for this session.")
    return None


def call_groq_api(prompt: str, temperature: float = 0.2, response_json: bool = True) -> str | None:
    import time
    import requests
    import config
    import logging
    logger = logging.getLogger("api_helpers")
    
    if getattr(config, "GROQ_FAILED", False) or not config.GROQ_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a precise assistant returning structured data."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    if response_json:
        payload["response_format"] = {"type": "json_object"}

    max_retries = 5
    base_delay = 2.0
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=45,
            )
            if resp.status_code == 429:
                # Rate limit hit, parse Retry-After header
                retry_after = resp.headers.get("Retry-After")
                # Fallback to float retry delay or calculate exponential backoff
                delay = float(retry_after) if retry_after and retry_after.replace('.', '', 1).isdigit() else (base_delay * (2 ** attempt))
                logger.warning(f"Groq API rate limit hit (429). Retrying in {delay:.2f}s (Attempt {attempt+1}/{max_retries})...")
                time.sleep(delay)
                continue
            
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Groq API call error: {e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying Groq API in {delay:.2f}s...")
                time.sleep(delay)
            else:
                config.GROQ_FAILED = True
                raise e
    return None
