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
    monkeypatch.setattr(config, "TTS_PROVIDER", "larvoice")
    monkeypatch.setattr(config, "VIETNAMESE_API_KEY", "mock_key")
    monkeypatch.setattr(config, "LARVOICE_API_URL", "https://mock.larvoice.com/api/v1/tts")

    called_larvoice = False

    def mock_call_larvoice(text_vi, voice_id, speed):
        nonlocal called_larvoice
        called_larvoice = True
        assert text_vi == "Xin chào"
        assert voice_id == "mock_voice"
        assert speed == 1.0
        return "https://mock.audio/url.wav", "lar_job_1"

    def mock_download_audio(url, path, **kwargs):
        assert url == "https://mock.audio/url.wav"
        return {"path": path, "audio_url": url, "attempts": 1, "retry_count": 0, "status_code": 200}

    class MockAudioSegment:
        def __len__(self):
            return 2000

        def export(self, path, format):
            pass

    import src.synthesizer_vi

    monkeypatch.setattr(src.synthesizer_vi, "_call_larvoice", mock_call_larvoice)
    monkeypatch.setattr(src.synthesizer_vi, "_download_audio", mock_download_audio)
    monkeypatch.setattr(src.synthesizer_vi, "is_valid_audio_file", lambda p: True)
    monkeypatch.setattr(src.synthesizer_vi.AudioSegment, "from_file", lambda p: MockAudioSegment())
    monkeypatch.setattr(src.synthesizer_vi.os, "replace", lambda src, dst: None)
    monkeypatch.setattr(src.synthesizer_vi.os.path, "exists", lambda p: False)

    res = synthesize_segment_vi("Xin chào", "output.wav", target_duration=5.0, voice_id="mock_voice")

    assert called_larvoice is True
    assert res["actual_duration"] == 2.0
    assert res["speed_adjusted"] is False
    assert res["rate_applied"] == "1.0x"
    assert res["job_id"] == "lar_job_1"


def test_synthesize_segment_vi_lucylab_routing(monkeypatch):
    monkeypatch.setattr(config, "TTS_PROVIDER", "lucylab")
    monkeypatch.setattr(config, "VIETNAMESE_API_KEY", "mock_key")

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

    def mock_download_audio(url, path, **kwargs):
        assert url == "https://mock.audio/lucylab.wav"
        assert kwargs["provider"] == "lucylab"
        assert kwargs["export_id"] == "export_123"
        return {"path": path, "audio_url": url, "attempts": 1, "retry_count": 0, "status_code": 200}

    class MockAudioSegment:
        def __len__(self):
            return 3000

        def export(self, path, format):
            pass

    import src.synthesizer_vi

    monkeypatch.setattr(src.synthesizer_vi, "_call_lucylab", mock_call_lucylab)
    monkeypatch.setattr(src.synthesizer_vi, "_wait_for_audio", mock_wait_for_audio)
    monkeypatch.setattr(src.synthesizer_vi, "_download_audio", mock_download_audio)
    monkeypatch.setattr(src.synthesizer_vi, "is_valid_audio_file", lambda p: True)
    monkeypatch.setattr(src.synthesizer_vi.AudioSegment, "from_file", lambda p: MockAudioSegment())
    monkeypatch.setattr(src.synthesizer_vi.os, "replace", lambda src, dst: None)
    monkeypatch.setattr(src.synthesizer_vi.os.path, "exists", lambda p: False)

    res = synthesize_segment_vi("Xin chào", "output.wav", target_duration=5.0, voice_id="mock_voice")

    assert called_lucylab is True
    assert res["actual_duration"] == 3.0
    assert res["speed_adjusted"] is False
    assert res["rate_applied"] == "1.0x"
    assert res["job_id"] == "export_123"
