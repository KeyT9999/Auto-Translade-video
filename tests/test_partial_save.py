import os
import json
import pytest
import config
from src.contextual_translator import translate_segments_contextual

def test_partial_save_and_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRANSLATION_WINDOW_SIZE", 2)
    monkeypatch.setattr(config, "TRANSLATION_CONTEXT_BEFORE", 1)
    monkeypatch.setattr(config, "TRANSLATION_CONTEXT_AFTER", 1)
    monkeypatch.setattr(config, "TRANSLATION_PARTIAL_SAVE_ENABLED", True)

    work_dir = str(tmp_path)
    windows_dir = os.path.join(work_dir, "translation_windows")
    os.makedirs(windows_dir, exist_ok=True)

    # Pre-populate window 1-2
    window_data = [
        {
            "id": 1,
            "source_text": "hello",
            "literal_vi": "chào",
            "dub_vi": "chào",
            "speaker": "NARRATOR",
            "speaker_gender": "neutral"
        },
        {
            "id": 2,
            "source_text": "world",
            "literal_vi": "thế giới",
            "dub_vi": "thế giới",
            "speaker": "NARRATOR",
            "speaker_gender": "neutral"
        }
    ]
    with open(os.path.join(windows_dir, "window_0001_0002.json"), "w", encoding="utf-8") as f:
        json.dump(window_data, f)

    segments = [
        {"id": 1, "text": "hello", "duration": 1.0, "start": 0.0, "end": 1.0},
        {"id": 2, "text": "world", "duration": 1.0, "start": 1.0, "end": 2.0},
        {"id": 3, "text": "python", "duration": 1.0, "start": 2.0, "end": 3.0},
        {"id": 4, "text": "programming", "duration": 1.0, "start": 3.0, "end": 4.0}
    ]

    called_count = 0
    from src.ai import ai_router
    def mock_translate(prompt, *a, **k):
        nonlocal called_count
        called_count += 1
        return {
            "segments": [
                {
                    "id": 3,
                    "source_text": "python",
                    "literal_vi": "mãng xà",
                    "dub_vi": "python",
                    "speaker": "NARRATOR",
                    "speaker_gender": "neutral"
                },
                {
                    "id": 4,
                    "source_text": "programming",
                    "literal_vi": "lập trình",
                    "dub_vi": "lập trình",
                    "speaker": "NARRATOR",
                    "speaker_gender": "neutral"
                }
            ]
        }
    monkeypatch.setattr(ai_router, "translate", mock_translate)

    res = translate_segments_contextual(
        segments, {}, {}, {}, "en", work_dir=work_dir
    )

    assert called_count == 1
    assert len(res) == 4
    assert res[0]["literal_vi"] == "chào"
    assert res[2]["literal_vi"] == "mãng xà"
    assert os.path.exists(os.path.join(windows_dir, "window_0003_0004.json"))
