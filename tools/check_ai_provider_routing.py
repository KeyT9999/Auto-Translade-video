import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.ai import ai_router

def main():
    print("=== Checking AI Provider Routing & Config ===")
    print(f"ASR Provider: {config.ASR_PROVIDER}")
    print(f"Translation Provider: {config.TRANSLATION_PROVIDER}")
    print(f"QA/Repair Provider: {config.QA_REPAIR_PROVIDER}")
    print(f"Gemini Enabled: {config.GEMINI_ENABLED}")
    
    print("\nFallback configurations:")
    print(f"Translation fallback: {config.TRANSLATION_FALLBACK_PROVIDERS}")
    print(f"QA/Repair fallback: {config.QA_REPAIR_FALLBACK_PROVIDERS}")

    print("\nValidating API keys...")
    try:
        config.validate_api_keys()
        print("API keys validation passed successfully!")
    except Exception as e:
        print(f"API keys validation warning/error: {e}")

    print("\nChecking Router Resolution...")
    try:
        translation_provider = ai_router.get_provider(config.TRANSLATION_PROVIDER)
        print(f"Active Translation Provider: {translation_provider.__class__.__name__ if translation_provider else 'None'}")
        
        repair_provider = ai_router.get_provider(config.QA_REPAIR_PROVIDER)
        print(f"Active QA/Repair Provider: {repair_provider.__class__.__name__ if repair_provider else 'None'}")
    except Exception as e:
        print(f"Error during router check: {e}")

if __name__ == "__main__":
    main()
