import logging
import pytest
from src.translator import build_translation_prompt, post_check_translation

def test_build_translation_prompt():
    segments = [
        {"id": 1, "text": "Hello", "duration": 2.0, "speaker": "ME", "speaker_gender": "female"},
        {"id": 2, "text": "Hi", "duration": 1.5}
    ]
    prompt = build_translation_prompt(segments, "en")
    
    # Assert segments are in prompt
    assert '"id": 1' in prompt
    assert '"speaker": "ME"' in prompt
    assert '"speaker_gender": "female"' in prompt
    assert '"id": 2' in prompt
    
    # Assert instructions are present
    assert "VIETNAMESE PRONOUN SYSTEM" in prompt
    assert "Mother to child" in prompt
    assert "TUYỆT ĐỐI KHÔNG" in prompt


def test_post_check_translation_family_pronouns(caplog):
    caplog.set_level(logging.WARNING, logger="translator")
    
    # ME speaker saying "tôi" and "bạn"
    segments = [
        {
            "id": 1,
            "text": "Ask your mother",
            "text_vi": "Tôi là mẹ của bạn.",
            "duration": 5.0,
            "speaker": "ME"
        }
    ]
    post_check_translation(segments)
    
    assert "contains inappropriate family pronoun 'tôi'" in caplog.text
    assert "contains inappropriate family pronoun 'bạn'" in caplog.text


def test_post_check_translation_chinese_slang(caplog):
    caplog.set_level(logging.WARNING, logger="translator")
    
    segments = [
        {
            "id": 2,
            "text": "Oh my god",
            "text_vi": "Aiya thật là mệt.",
            "duration": 5.0
        }
    ]
    post_check_translation(segments)
    assert "contains suspected Chinese transliteration" in caplog.text


def test_post_check_translation_chinese_characters(caplog):
    caplog.set_level(logging.WARNING, logger="translator")
    
    segments = [
        {
            "id": 3,
            "text": "Okay",
            "text_vi": "Được rồi 嗯",
            "duration": 5.0
        }
    ]
    post_check_translation(segments)
    assert "contains leftover Chinese characters" in caplog.text


def test_post_check_translation_isolated_hao(caplog):
    caplog.set_level(logging.WARNING, logger="translator")
    
    # Standalone "hảo" should flag
    segments_bad = [
        {
            "id": 4,
            "text": "Good",
            "text_vi": "Hảo.",
            "duration": 2.0
        }
    ]
    post_check_translation(segments_bad)
    assert "contains isolated word 'hảo'" in caplog.text
    
    caplog.clear()
    
    # "hảo hảo" should NOT flag
    segments_good = [
        {
            "id": 5,
            "text": "Noodles",
            "text_vi": "Tôi thích ăn mì Hảo Hảo.",
            "duration": 5.0
        }
    ]
    post_check_translation(segments_good)
    assert "contains isolated word 'hảo'" not in caplog.text


def test_post_check_translation_char_rate(caplog):
    caplog.set_level(logging.WARNING, logger="translator")
    
    # Character rate too high (len=64, duration=1.0 -> 64 chars/sec)
    segments = [
        {
            "id": 6,
            "text": "Fast talk",
            "text_vi": "Đây là một câu nói cực kỳ dài và sẽ không thể nhét vừa được đâu.",
            "duration": 1.0
        }
    ]
    post_check_translation(segments)
    assert "has high character rate" in caplog.text


def test_post_check_translation_untranslated(caplog):
    caplog.set_level(logging.WARNING, logger="translator")
    
    segments = [
        {
            "id": 7,
            "text": "This is identical text",
            "text_vi": "This is identical text",
            "duration": 5.0
        }
    ]
    post_check_translation(segments)
    assert "Translation is identical to original text" in caplog.text
