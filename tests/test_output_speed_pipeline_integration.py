import os
import sys
import pytest
import logging
from unittest.mock import MagicMock
import pipeline_vi

def test_pipeline_output_speed_integration(tmp_path, monkeypatch):
    work_dir = tmp_path / "VN" / "test_session_speed"
    os.makedirs(work_dir, exist_ok=True)

    dummy_video_path = os.path.join(str(tmp_path), "dummy_video.mp4")
    with open(dummy_video_path, "w", encoding="utf-8") as f:
        f.write("mock video content")

    dummy_audio_path = os.path.join(str(work_dir), "original_audio.wav")
    with open(dummy_audio_path, "w", encoding="utf-8") as f:
        f.write("mock audio content")

    # Mock low-level dependencies
    monkeypatch.setattr(pipeline_vi, "_resolve_video", lambda w, u, f: dummy_video_path)
    monkeypatch.setattr(pipeline_vi, "extract_audio", lambda v, a: None)
    monkeypatch.setattr(pipeline_vi.config, "GEMINI_ENABLED", False)
    monkeypatch.setattr(pipeline_vi.config, "GOOGLE_API_KEY", "")
    monkeypatch.setattr(pipeline_vi.config, "GROQ_API_KEY", "")

    mock_segments = [
        {"id": 1, "text": "Hello world", "start": 0.0, "end": 2.0, "duration": 2.0}
    ]
    monkeypatch.setattr(pipeline_vi, "transcribe", lambda a, l: mock_segments)

    # Use sys.modules to mock locally-imported submodules
    mock_context_builder = MagicMock()
    mock_context_builder.build_video_context.return_value = {"translation_style": "spoken Vietnamese"}
    monkeypatch.setitem(sys.modules, "src.context_builder", mock_context_builder)

    mock_glossary_builder = MagicMock()
    mock_glossary_builder.build_glossary.return_value = {}
    monkeypatch.setitem(sys.modules, "src.glossary_builder", mock_glossary_builder)

    mock_character_profiler = MagicMock()
    mock_character_profiler.build_character_bible.return_value = {}
    mock_character_profiler.sanitize_character_bible.return_value = {}
    monkeypatch.setitem(sys.modules, "src.character_profiler", mock_character_profiler)

    mock_translator = MagicMock()
    mock_translator.translate_segments_contextual.return_value = [
        {"id": 1, "text": "Hello world", "text_vi": "Xin chào thế giới", "start": 0.0, "end": 2.0, "duration": 2.0}
    ]
    monkeypatch.setitem(sys.modules, "src.contextual_translator", mock_translator)

    mock_validator = MagicMock()
    mock_validator.validate_translation.return_value = {
        "bad_segments": 0, "issues": []
    }
    mock_validator.has_blocking_errors.return_value = False
    mock_validator.filter_repairable_issues.return_value = []
    monkeypatch.setitem(sys.modules, "src.translation_validator", mock_validator)

    # Mock subtitle rendering & merging
    def mock_render(video_path, ass_path, output_path, cover_cfg=None, logo_cfg=None):
        with open(output_path, "w") as f:
            f.write("mock rendered video")
    
    import src.subtitle_renderer
    monkeypatch.setattr(src.subtitle_renderer, "render_video_with_cover", mock_render)

    # Mock output speed FFmpeg call so we don't spawn a subprocess
    speed_called = False
    def mock_apply_playback_speed_to_video(input_video, output_video, speed, overwrite=True):
        nonlocal speed_called
        speed_called = True
        with open(output_video, "w") as f:
            f.write("mock speed adjusted video")
        return output_video

    import src.output_speed
    monkeypatch.setattr(src.output_speed, "apply_playback_speed_to_video", mock_apply_playback_speed_to_video)

    # Run the pipeline with speed 1.2
    report = pipeline_vi.run_pipeline_vi(
        url=None,
        file_path=dummy_video_path,
        source_lang="en-US",
        voice_id="vi_vn_002",
        skip_video=False,
        output_dir=str(tmp_path / "VN"),
        resume_dir=str(work_dir),
        publish_youtube=False,
        publish_facebook=False,
        burn_subtitles=True,
        mode="subtitle_only",
        output_playback_speed=1.2,
    )

    # Assertions
    assert speed_called is True
    assert report["status"] == "success"
    assert report["output_playback_speed"] == 1.2
    assert report["speed_adjusted"] is True
    assert report["files"]["rendered_video_original_speed"].endswith("subtitled_video.mp4")
    assert report["files"]["rendered_video_final"].endswith("subtitled_video_1.2x.mp4")
    assert report["files"]["transcript_vi_speed_srt"].endswith("transcript_vi_1.2x.srt")
    assert report["files"]["transcript_vi_speed_json"].endswith("transcript_vi_1.2x.json")
