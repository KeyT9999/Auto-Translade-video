import os
import sys
from dotenv import load_dotenv
import requests

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY is not set in .env")
    sys.exit(1)

# Mask the API key for display
masked_key = api_key[:12] + "..." + api_key[-6:] if len(api_key) > 18 else api_key
print(f"Testing OpenAI API key: {masked_key}")

url = "https://api.openai.com/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
payload = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 5
}

try:
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    if response.status_code == 200:
        print("Success! The OpenAI API key is active and has credits.")
        print("Response:", response.json()["choices"][0]["message"]["content"].strip())
    else:
        print(f"API Error (HTTP {response.status_code}):")
        print(response.text)
except Exception as e:
    print(f"Connection failed: {e}")
