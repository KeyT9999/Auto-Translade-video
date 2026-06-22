import json
import os

import pytest
import requests

import config
import src.contextual_translator as contextual_translator
from src.contextual_translator import (
    TranslationPendingError,
    get_translation_window_status,
    translate_segments_contextual,
)


def test_resume_only_retries_failed_window(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRANSLATION_ADAPTIVE_WINDOW_ENABLED", False)
    monkeypatch.setattr(config, "TRANSLATION_WINDOW_SIZE", 2)
    monkeypatch.setattr(config, "TRANSLATION_MIN_WINDOW_SIZE", 2)
    monkeypatch.setattr(config, "TRANSLATION_ON_TIMEOUT_SPLIT_WINDOW", True)
    monkeypatch.setattr(config, "TRANSLATION_PARTIAL_SAVE_ENABLED", True)
    monkeypatch.setattr(config, "TRANSLATION_CACHE_ENABLED", False)
    monkeypatch.setattr(config, "TRANSLATION_CONTEXT_BEFORE", 0)
    monkeypatch.setattr(config, "TRANSLATION_CONTEXT_AFTER", 0)
    monkeypatch.setattr(contextual_translator.time, "sleep", lambda *_: None)

    segments = [
        {"id": 1, "text": "one", "duration": 1.0, "start": 0.0, "end": 1.0},
        {"id": 2, "text": "two", "duration": 1.0, "start": 1.0, "end": 2.0},
        {"id": 3, "text": "three", "duration": 1.0, "start": 2.0, "end": 3.0},
        {"id": 4, "text": "four", "duration": 1.0, "start": 3.0, "end": 4.0},
    ]
    by_id = {seg["id"]: seg for seg in segments}

    from src.ai import ai_router

    first_run_calls: list[str] = []

    def first_run_translate(prompt, request_label=None, **kwargs):
        first_run_calls.append(request_label)
        if request_label == "window 0003_0004":
            raise requests.ReadTimeout("Read timed out")

        start_id, end_id = [int(part) for part in request_label.split()[1].split("_")]
        return {
            "segments": [
                {
                    "id": seg_id,
                    "source_text": by_id[seg_id]["text"],
                    "literal_vi": f"literal-{seg_id}",
                    "dub_vi": f"dub-{seg_id}",
                    "speaker": "NARRATOR",
                    "speaker_gender": "neutral",
                }
                for seg_id in range(start_id, end_id + 1)
            ]
        }

    monkeypatch.setattr(ai_router, "translate", first_run_translate)

    with pytest.raises(TranslationPendingError) as exc_info:
        translate_segments_contextual(
            segments,
            {"translation_style": "spoken Vietnamese"},
            {},
            {},
            "en-US",
            work_dir=str(tmp_path),
        )

    assert first_run_calls == ["window 0001_0002", "window 0003_0004"]
    assert exc_info.value.failed_windows[0]["range"] == "0003_0004"

    completed_window_path = tmp_path / "translation_windows" / "window_0001_0002.json"
    assert completed_window_path.exists()
    with open(completed_window_path, "r", encoding="utf-8") as handle:
        completed_window = json.load(handle)
    assert [item["id"] for item in completed_window] == [1, 2]

    status = get_translation_window_status(str(tmp_path))
    assert status is not None
    assert status["completed_windows"] == ["0001_0002"]
    assert status["failed_windows"] == ["0003_0004"]

    second_run_calls: list[str] = []

    def second_run_translate(prompt, request_label=None, **kwargs):
        second_run_calls.append(request_label)
        assert request_label == "window 0003_0004"
        return {
            "segments": [
                {
                    "id": seg_id,
                    "source_text": by_id[seg_id]["text"],
                    "literal_vi": f"literal-{seg_id}",
                    "dub_vi": f"dub-{seg_id}",
                    "speaker": "NARRATOR",
                    "speaker_gender": "neutral",
                }
                for seg_id in range(3, 5)
            ]
        }

    monkeypatch.setattr(ai_router, "translate", second_run_translate)

    translated = translate_segments_contextual(
        segments,
        {"translation_style": "spoken Vietnamese"},
        {},
        {},
        "en-US",
        work_dir=str(tmp_path),
    )

    assert second_run_calls == ["window 0003_0004"]
    assert [seg["id"] for seg in translated] == [1, 2, 3, 4]

    final_status = get_translation_window_status(str(tmp_path))
    assert final_status is not None
    assert final_status["failed_windows"] == []
    assert sorted(final_status["completed_windows"]) == ["0001_0002", "0003_0004"]
