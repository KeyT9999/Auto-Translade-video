import pytest
import config
from src.speaker_detector import get_voice_id_for_segment

def test_get_voice_id_for_segment_hierarchical(monkeypatch):
    default_voice = "female"
    
    # 1. Custom voice map passed at runtime has highest priority
    seg = {"speaker": "NV_CHINH", "speaker_gender": "male"}
    runtime_map = {"NV_CHINH": "custom_runtime_id"}
    assert get_voice_id_for_segment(seg, default_voice, runtime_map) == "custom_runtime_id"
    
    # 2. VOICE_CHARACTER_MAP config has second priority
    monkeypatch.setattr(config, "VOICE_CHARACTER_MAP", {"NV_CHINH": "config_mapped_id"})
    assert get_voice_id_for_segment(seg, default_voice) == "config_mapped_id"
    
    # 3. VOICE_NARRATOR config has third priority for NARRATOR speaker
    monkeypatch.setattr(config, "VOICE_NARRATOR", "narrator_voice_id")
    seg_narrator = {"speaker": "NARRATOR", "speaker_gender": "neutral"}
    assert get_voice_id_for_segment(seg_narrator, default_voice) == "narrator_voice_id"
    
    # 4. Gender-based fallback
    monkeypatch.setattr(config, "VIETNAMESE_VOICEID_MALE", "default_male_id")
    monkeypatch.setattr(config, "VIETNAMESE_VOICEID_FEMALE", "default_female_id")
    # Clean up mapping configs so we hit gender fallback
    monkeypatch.setattr(config, "VOICE_CHARACTER_MAP", {})
    monkeypatch.setattr(config, "VOICE_NARRATOR", "")
    
    seg_male = {"speaker": "NV_CHINH", "speaker_gender": "male"}
    assert get_voice_id_for_segment(seg_male, default_voice) == "default_male_id"
    
    seg_female = {"speaker": "NV_PHU", "speaker_gender": "female"}
    assert get_voice_id_for_segment(seg_female, default_voice) == "default_female_id"
    
    # 5. Default voice fallback when no gender and no map match
    seg_neutral = {"speaker": "UNKNOWN", "speaker_gender": "neutral"}
    assert get_voice_id_for_segment(seg_neutral, default_voice) == default_voice


def test_get_voice_id_for_segment_custom_voice(monkeypatch):
    # Set default male and female voice IDs in config
    monkeypatch.setattr(config, "VIETNAMESE_VOICEID_MALE", "default_male_id")
    monkeypatch.setattr(config, "VIETNAMESE_VOICEID_FEMALE", "default_female_id")
    # Clean up mappings
    monkeypatch.setattr(config, "VOICE_CHARACTER_MAP", {})
    monkeypatch.setattr(config, "VOICE_NARRATOR", "")

    # Case 1: default voice is custom (neither standard male/female id nor 'male'/'female')
    custom_voice = "hue"
    
    seg_female = {"speaker": "NARRATOR", "speaker_gender": "female"}
    assert get_voice_id_for_segment(seg_female, custom_voice) == "hue"

    seg_male = {"speaker": "NARRATOR", "speaker_gender": "male"}
    assert get_voice_id_for_segment(seg_male, custom_voice) == "hue"

    # Case 2: default voice is standard 'female' - should fallback to default_male_id for male segment
    assert get_voice_id_for_segment(seg_male, "female") == "default_male_id"
    assert get_voice_id_for_segment(seg_female, "female") == "default_female_id"

