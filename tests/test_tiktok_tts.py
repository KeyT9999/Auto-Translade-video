import pytest
import config
import requests
from src.synthesizer_vi import synthesize_segment_vi, TTSSegmentError


def test_synthesize_segment_vi_tiktok_routing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "TTS_PROVIDER", "tiktok")
    monkeypatch.setattr(config, "TIKTOK_SESSION_ID", "mock_session_id")
    monkeypatch.setattr(config, "VIETNAMESE_API_KEY", "mock_session_id")
    
    called_tiktok = False
    
    class MockResponse:
        status_code = 200
        def json(self):
            import base64
            dummy_bytes = b"fake audio content"
            return {
                "status_code": 0,
                "message": "success",
                "data": {
                    "v_str": base64.b64encode(dummy_bytes).decode("utf-8")
                }
            }
        def raise_for_status(self):
            pass
            
    def mock_post(url, params=None, headers=None, timeout=None):
        nonlocal called_tiktok
        called_tiktok = True
        assert url == "https://api16-normal-c-useast1a.tiktokv.com/media/api/text/speech/invoke/"
        assert params["req_text"] == "Xin chào"
        assert params["text_speaker"] == "BV074_streaming"
        assert headers["Cookie"] == "sessionid=mock_session_id"
        return MockResponse()
        
    class MockAudioSegment:
        def __len__(self):
            return 1500
        def export(self, path, format):
            with open(path, "wb") as f:
                f.write(b"mocked wav")
                
    import src.synthesizer_vi
    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(src.synthesizer_vi, "is_valid_audio_file", lambda p: True)
    monkeypatch.setattr(src.synthesizer_vi.AudioSegment, "from_file", lambda p: MockAudioSegment())
    monkeypatch.setattr(src.synthesizer_vi.os, "replace", lambda src, dst: None)
    
    output_wav = tmp_path / "output.wav"
    res = synthesize_segment_vi("Xin chào", str(output_wav), voice_id="vi_vn_002")
    
    assert called_tiktok is True
    assert res["provider"] == "tiktok"
    assert res["voice_id"] == "BV074_streaming"
    assert res["actual_duration"] == 1.5
    assert res["status"] == "generated"


def test_synthesize_segment_vi_tiktok_api_error(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "TTS_PROVIDER", "tiktok")
    monkeypatch.setattr(config, "TIKTOK_SESSION_ID", "mock_session_id")
    monkeypatch.setattr(config, "VIETNAMESE_API_KEY", "mock_session_id")
    
    class MockErrorResponse:
        status_code = 200
        def json(self):
            return {
                "status_code": 1,
                "message": "Couldn't load speech"
            }
        def raise_for_status(self):
            pass
            
    def mock_post(url, params=None, headers=None, timeout=None):
        return MockErrorResponse()
        
    import src.synthesizer_vi
    monkeypatch.setattr(requests, "post", mock_post)
    
    output_wav = tmp_path / "output.wav"
    with pytest.raises(TTSSegmentError, match="TikTok TTS API returned error"):
        synthesize_segment_vi("Xin chào", str(output_wav), voice_id="vi_vn_002")
