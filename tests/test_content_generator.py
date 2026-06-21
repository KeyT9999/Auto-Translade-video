import config
from src import content_generator


def test_generate_youtube_metadata_respects_gemini_disabled(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_ENABLED", False)

    gemini_called = False

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            nonlocal gemini_called
            gemini_called = True

    monkeypatch.setattr(content_generator.genai, "Client", _FakeClient)
    monkeypatch.setattr(
        content_generator,
        "_generate_metadata_groq",
        lambda prompt: '{"title": "Tieu de", "description": "Mo ta", "hashtags": ["#a"]}',
    )

    metadata = content_generator.generate_youtube_metadata(
        script_original="hello",
        script_translated="xin chao",
        target_lang="vi-VN",
        source_url="",
        api_key="gemini-key-still-present",
        model_id="gemini-2.0-flash",
    )

    assert gemini_called is False
    assert metadata["title"] == "Tieu de"
    assert metadata["hashtags"] == ["#a"]
