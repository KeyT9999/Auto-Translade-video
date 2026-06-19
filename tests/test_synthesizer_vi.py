import pytest
import config
from src.synthesizer_vi import synthesize_segment_vi

def test_synthesizer_vi_requires_voice_id():
    with pytest.raises(ValueError, match="voice_id is required"):
        synthesize_segment_vi("Xin chào", "output.wav", voice_id=None)

def test_synthesizer_vi_requires_api_key(monkeypatch):
    monkeypatch.setattr(config, "VIETNAMESE_API_KEY", "")
    with pytest.raises(ValueError, match="VIETNAMESE_API_KEY / LARVOICE_API_KEY not set"):
        synthesize_segment_vi("Xin chào", "output.wav", voice_id="1")

def test_synthesize_segment_vi_larvoice_routing(monkeypatch):
    # Mock config
    monkeypatch.setattr(config, "TTS_PROVIDER", "larvoice")
    monkeypatch.setattr(config, "VIETNAMESE_API_KEY", "mock_key")
    monkeypatch.setattr(config, "LARVOICE_API_URL", "https://mock.larvoice.com/api/v1/tts")
    
    # Mock calls
    called_larvoice = False
    
    def mock_call_larvoice(text_vi, voice_id, speed):
        nonlocal called_larvoice
        called_larvoice = True
        assert text_vi == "Xin chào"
        assert voice_id == "mock_voice"
        assert speed == 1.0
        return "https://mock.audio/url.wav"
        
    def mock_download_audio(url, path):
        assert url == "https://mock.audio/url.wav"
        return path
        
    class MockAudioSegment:
        def __len__(self):
            return 2000 # 2 seconds
            
        def export(self, path, format):
            pass
            
    # Apply mocks to module
    import src.synthesizer_vi
    monkeypatch.setattr(src.synthesizer_vi, "_call_larvoice", mock_call_larvoice)
    monkeypatch.setattr(src.synthesizer_vi, "_download_audio", mock_download_audio)
    monkeypatch.setattr(src.synthesizer_vi.AudioSegment, "from_file", lambda p: MockAudioSegment())
    monkeypatch.setattr(src.synthesizer_vi.os, "remove", lambda p: None)
    
    res = synthesize_segment_vi("Xin chào", "output.wav", target_duration=5.0, voice_id="mock_voice")
    
    assert called_larvoice is True
    assert res["actual_duration"] == 2.0
    assert res["speed_adjusted"] is False
    assert res["rate_applied"] == "1.0x"

def test_synthesize_segment_vi_lucylab_routing(monkeypatch):
    # Mock config
    monkeypatch.setattr(config, "TTS_PROVIDER", "lucylab")
    monkeypatch.setattr(config, "VIETNAMESE_API_KEY", "mock_key")
    
    # Mock calls
    called_lucylab = False
    
    def mock_call_lucylab(method, input_data):
        nonlocal called_lucylab
        called_lucylab = True
        assert method == "ttsLongText"
        assert input_data["text"] == "Xin chào"
        assert input_data["userVoiceId"] == "mock_voice"
        return {"projectExportId": "export_123"}
        
    def mock_wait_for_audio(export_id):
        assert export_id == "export_123"
        return "https://mock.audio/lucylab.wav"
        
    def mock_download_audio(url, path):
        assert url == "https://mock.audio/lucylab.wav"
        return path
        
    class MockAudioSegment:
        def __len__(self):
            return 3000 # 3 seconds
            
        def export(self, path, format):
            pass
            
    # Apply mocks to module
    import src.synthesizer_vi
    monkeypatch.setattr(src.synthesizer_vi, "_call_lucylab", mock_call_lucylab)
    monkeypatch.setattr(src.synthesizer_vi, "_wait_for_audio", mock_wait_for_audio)
    monkeypatch.setattr(src.synthesizer_vi, "_download_audio", mock_download_audio)
    monkeypatch.setattr(src.synthesizer_vi.AudioSegment, "from_file", lambda p: MockAudioSegment())
    monkeypatch.setattr(src.synthesizer_vi.os, "remove", lambda p: None)
    
    res = synthesize_segment_vi("Xin chào", "output.wav", target_duration=5.0, voice_id="mock_voice")
    
    assert called_lucylab is True
    assert res["actual_duration"] == 3.0
    assert res["speed_adjusted"] is False
    assert res["rate_applied"] == "1.0x"
