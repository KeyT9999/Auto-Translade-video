"""Unit tests for contextual translation features: context building, validation, repair, and rewriting."""
import os
import json
import pytest
from src.translation_validator import validate_translation
from src.translation_repair import repair_translation
from src.timeline_rewriter import rewrite_timeline
from src.context_builder import build_video_context
from src.glossary_builder import build_glossary
from src.character_profiler import build_character_bible


@pytest.fixture
def sample_segments():
    return [
        {"id": 1, "text": "你好", "start": 0.0, "end": 2.0, "duration": 2.0, "literal_vi": "Xin chào", "dub_vi": "Xin chào mọi người", "speaker": "SPEAKER_00", "speaker_gender": "male"},
        {"id": 2, "text": "坐电梯", "start": 2.1, "end": 3.0, "duration": 0.9, "literal_vi": "Đi thang máy", "dub_vi": "Đi thang máy", "speaker": "SPEAKER_00", "speaker_gender": "male"},
        {"id": 3, "text": "坐 thang máy lên 75 楼", "start": 3.1, "end": 6.5, "duration": 3.4, "literal_vi": "Đi thang máy lên lầu 75", "dub_vi": "Đi thang máy lên lầu 75 坐", "speaker": "SPEAKER_00", "speaker_gender": "male"},
        {"id": 4, "text": "这里很漂亮", "start": 6.6, "end": 12.0, "duration": 5.4, "literal_vi": "Ở đây rất đẹp", "dub_vi": "Đâu cũng có thể ngồi", "speaker": "SPEAKER_00", "speaker_gender": "male"}
    ]


@pytest.fixture
def mock_profiles():
    video_context = {
        "video_type": "vlog",
        "topic": "traveling",
        "setting": "building",
        "speaker_style": "casual",
        "narration_pov": "first-person",
        "tone": "cheerful",
        "translation_style": "spoken Vietnamese",
        "entities": [],
        "deixis_policy": {"这里": "ở đây / chỗ này"},
        "pronoun_policy": {"self": "mình", "other": "mọi người"}
    }
    glossary = {
        "terms": {
            "这里": "ở đây",
            "电梯": "thang máy",
            "楼": "tầng"
        }
    }
    character_bible = {
        "characters": [
            {
                "speaker_id": "SPEAKER_00",
                "role": "narrator",
                "gender": "male",
                "age": "adult",
                "personality": "casual",
                "vi_pronoun_self": "mình",
                "vi_pronoun_other": "mọi người",
                "voice_id": None
            }
        ],
        "global_pronoun_rules": {"我们": "mình"}
    }
    return video_context, glossary, character_bible


def test_validator_cjk_leak(sample_segments):
    report = validate_translation(sample_segments)
    issues = report["issues"]
    
    # Segment 3 has CJK character '坐' in dub_vi
    cjk_issues = [iss for iss in issues if iss["type"] == "SOURCE_LANGUAGE_LEAK"]
    assert len(cjk_issues) == 1
    assert cjk_issues[0]["id"] == 3
    assert cjk_issues[0]["field"] == "dub_vi"


def test_validator_awkward_phrasing(sample_segments):
    report = validate_translation(sample_segments)
    issues = report["issues"]
    
    # Segment 4 has awkward phrase "Đâu cũng có thể ngồi"
    awkward = [iss for iss in issues if iss["type"] == "AWKWARD_TRANSLATION"]
    assert len(awkward) >= 1
    assert any(iss["id"] == 4 for iss in awkward)


def test_validator_timing_overflow(sample_segments):
    # Make segment 2 extremely long to trigger overflow check (>15 chars/sec)
    overflow_segs = [
        {"id": 2, "text": "坐电梯", "start": 2.1, "end": 3.0, "duration": 0.5, "literal_vi": "Đi thang máy", "dub_vi": "Tôi đang chuẩn bị đi thang máy lên lầu 75 để ăn tối cùng bạn bè", "speaker": "SPEAKER_00", "speaker_gender": "male"}
    ]
    report = validate_translation(overflow_segs)
    issues = report["issues"]
    
    overflow = [iss for iss in issues if iss["type"] == "TIMING_OVERFLOW"]
    assert len(overflow) == 1


def test_timeline_rewriter_no_change():
    # If segments have normal character rate, they shouldn't change
    segs = [
        {"id": 1, "text": "hello", "start": 0.0, "end": 2.0, "duration": 2.0, "dub_vi": "Xin chào"}
    ]
    context = {"video_type": "vlog"}
    bible = {"characters": []}
    
    rewritten = rewrite_timeline(segs, context, bible)
    assert rewritten[0]["final_dub_vi"] == "Xin chào"
    assert rewritten[0]["timing_rewrite_applied"] is False


def test_build_profiles_fallbacks(tmp_path, monkeypatch):
    # Mock AIRouter to fail so that fallback files are created
    from src.ai import ai_router
    def mock_fail(*a, **k):
        raise ValueError("mock failure")
    monkeypatch.setattr(ai_router, "generate_context", mock_fail)
    monkeypatch.setattr(ai_router, "generate_glossary", mock_fail)
    monkeypatch.setattr(ai_router, "generate_character_bible", mock_fail)

    # Test fallback files creation when empty segments list is provided
    context_path = str(tmp_path / "video_context.json")
    glossary_path = str(tmp_path / "glossary.json")
    bible_path = str(tmp_path / "character_bible.json")

    build_video_context([], context_path)
    build_glossary([], {}, glossary_path)
    build_character_bible([], {}, bible_path)

    assert os.path.exists(context_path)
    assert os.path.exists(glossary_path)
    assert os.path.exists(bible_path)

    with open(context_path, encoding="utf-8") as f:
        data = json.load(f)
        assert "video_type" in data
