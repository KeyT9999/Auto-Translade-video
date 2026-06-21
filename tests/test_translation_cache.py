import os
import json
import pytest
import config
from pipeline_vi import (
    compute_translation_cache_hash,
    get_translation_from_cache,
    save_translation_to_cache
)

def test_translation_cache_workflow(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRANSLATION_CACHE_ENABLED", True)
    monkeypatch.chdir(tmp_path)

    segments = [{"id": 1, "text": "hello"}]
    source_lang = "en"
    translation_style = "spoken"

    # Compute hash
    cache_hash = compute_translation_cache_hash(segments, source_lang, translation_style)
    assert isinstance(cache_hash, str)
    assert len(cache_hash) == 64

    # Cache should miss
    assert get_translation_from_cache(cache_hash) is None

    # Save to cache
    translated_data = [{"id": 1, "text": "hello", "text_vi": "chào"}]
    save_translation_to_cache(cache_hash, translated_data)

    # Cache should hit
    hit_data = get_translation_from_cache(cache_hash)
    assert hit_data == translated_data

    # Disable cache
    monkeypatch.setattr(config, "TRANSLATION_CACHE_ENABLED", False)
    assert get_translation_from_cache(cache_hash) is None
