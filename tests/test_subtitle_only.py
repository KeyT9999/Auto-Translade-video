import os
import json
import pytest
from unittest.mock import MagicMock
import pipeline_vi

def test_subtitle_only_mode_execution(tmp_path, monkeypatch):
    # Setup paths and dummy files
    work_dir = tmp_path / "VN" / "test_session_vi"
    os.makedirs(work_dir, exist_ok=True)
    
    dummy_video_path = os.path.join(str(tmp_path), "dummy_video.mp4")
    with open(dummy_video_path, "w") as f:
        f.write("mock video content")
        
    dummy_audio_path = os.path.join(str(work_dir), "original_audio.wav")
    with open(dummy_audio_path, "w") as f:
        f.write("mock audio content")

    # Mock all external dependencies of the pipeline
    monkeypatch.setattr(pipeline_vi, "_resolve_video", lambda w, u, f: dummy_video_path)
    monkeypatch.setattr(pipeline_vi, "extract_audio", lambda v, a: None)
    
    # Mock ASR transcribe
    mock_segments = [
        {"id": 1, "text": "Hello world", "start": 0.0, "end": 2.0, "duration": 2.0}
    ]
    monkeypatch.setattr(pipeline_vi, "transcribe", lambda a, l: mock_segments)
    
    # Mock translation fallback/contextual translation (by patching the files, or we can just mock contextual translator)
    mock_translated_segments = [
        {"id": 1, "text": "Hello world", "text_vi": "Xin chào thế giới", "start": 0.0, "end": 2.0, "duration": 2.0}
    ]
    
    # We will mock the contextual translator, validator, rewriter, etc. if pipeline tries to run it,
    # or just let fallback happen. But to avoid Gemini calls, let's mock the whole translation block
    # or contextual translate functions.
    import sys
    # Mock context_builder, glossary_builder, character_profiler, contextual_translator, translation_validator, timeline_rewriter
    monkeypatch.setitem(sys.modules, "src.context_builder", MagicMock())
    monkeypatch.setitem(sys.modules, "src.glossary_builder", MagicMock())
    monkeypatch.setitem(sys.modules, "src.character_profiler", MagicMock())
    
    mock_translator_module = MagicMock()
    mock_translator_module.translate_segments_contextual.return_value = mock_translated_segments
    monkeypatch.setitem(sys.modules, "src.contextual_translator", mock_translator_module)
    
    mock_validator_module = MagicMock()
    mock_validator_module.validate_translation.return_value = {"bad_segments": 0, "issues": []}
    monkeypatch.setitem(sys.modules, "src.translation_validator", mock_validator_module)
    
    mock_rewriter_module = MagicMock()
    mock_rewriter_module.rewrite_timeline.return_value = mock_translated_segments
    monkeypatch.setitem(sys.modules, "src.timeline_rewriter", mock_rewriter_module)

    # Mock speaker detection
    monkeypatch.setattr(pipeline_vi, "detect_speakers", lambda segs: [
        dict(s, speaker="NARRATOR", speaker_gender="neutral") for s in segs
    ])

    # Trace calls to functions that must NOT be called in subtitle_only mode
    separate_vocals_called = False
    def mock_separate_vocals(a, w):
        nonlocal separate_vocals_called
        separate_vocals_called = True
        return {"no_vocals": None}
    monkeypatch.setattr(pipeline_vi, "separate_vocals", mock_separate_vocals)

    synthesize_called = False
    def mock_synthesize(text_vi, output_path, target_duration, voice_id):
        nonlocal synthesize_called
        synthesize_called = True
        return {"path": output_path, "actual_duration": target_duration, "speed_adjusted": False}
    monkeypatch.setattr(pipeline_vi, "synthesize_segment_vi", mock_synthesize)

    merge_segments_called = False
    def mock_merge_segments(segs, fit_dir, out, duration, background_path, background_gain_db):
        nonlocal merge_segments_called
        merge_segments_called = True
    monkeypatch.setattr(pipeline_vi, "merge_segments", mock_merge_segments)

    merge_video_called = False
    def mock_merge_video(v, a, o, srt_path):
        nonlocal merge_video_called
        merge_video_called = True
    monkeypatch.setattr(pipeline_vi, "merge_video", mock_merge_video)

    # Trace burn subtitles which MUST be called
    burn_subtitles_called = False
    def mock_burn_subtitles(v, srt, o):
        nonlocal burn_subtitles_called
        burn_subtitles_called = True
        # Create output file
        with open(o, "w") as f:
            f.write("mock subtitled video")
        return o
    import src.video_merger
    monkeypatch.setattr(src.video_merger, "burn_subtitles_to_video", mock_burn_subtitles)

    # Run the pipeline under subtitle_only mode
    report = pipeline_vi.run_pipeline_vi(
        url=None,
        file_path="mock_file.mp4",
        source_lang="en-US",
        voice_id="female",
        skip_video=False,
        output_dir=str(tmp_path / "VN"),
        resume_dir=None,
        bg_mode="demucs",
        bg_duck_db=-12.0,
        publish_youtube=False,
        publish_facebook=False,
        pause_for_speakers=False,
        speaker_map=None,
        burn_subtitles=True,
        mode="subtitle_only"
    )

    # Assertions
    assert report["mode"] == "subtitle_only"
    assert not separate_vocals_called, "Should skip Demucs vocal separation"
    assert not synthesize_called, "Should skip TTS synthesis"
    assert not merge_segments_called, "Should skip audio segment merging"
    assert not merge_video_called, "Should skip regular video merging (dubbing)"
    assert burn_subtitles_called, "Should burn subtitles to video"
    
    # Assert output video is correct
    subtitled_video_path = os.path.join(report["output_dir"], "subtitled_video.mp4")
    assert report["files"]["dubbed_video"] == subtitled_video_path
    assert os.path.exists(subtitled_video_path)

    # Verify report JSON file was written and contains correct fields
    report_json_path = os.path.join(report["output_dir"], "report.json")
    assert os.path.exists(report_json_path)
    with open(report_json_path, encoding="utf-8") as f:
        saved_report = json.load(f)
    assert saved_report["mode"] == "subtitle_only"
    assert saved_report["files"]["audio_vi_full"] is None
    assert saved_report["files"]["dubbed_video"] == subtitled_video_path


def test_transcribe_auto_language(monkeypatch):
    import src.transcriber
    import requests
    
    # Mock requests.post to verify lang_iso handling
    mock_post = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"segments": [{"start": 0.0, "end": 2.0, "text": "Test"}]}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response
    
    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(os.path, "exists", lambda x: True)
    
    # Mock open and subprocess
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MagicMock(returncode=0))
    
    # We need a context manager mock for open
    import builtins
    mock_open_instance = MagicMock()
    # Mock file read
    mock_open = MagicMock(return_value=mock_open_instance)
    monkeypatch.setattr(builtins, "open", mock_open)
    
    # Temporarily set API KEY so that transcribe_groq runs
    import config
    old_key = config.GROQ_API_KEY
    config.GROQ_API_KEY = "mock_key"
    
    try:
        # Call with "auto"
        res = src.transcriber.transcribe_groq("dummy.wav", "auto")
        assert res is not None
        # Verify language is NOT in post data payload
        assert mock_post.called
        args, kwargs = mock_post.call_args
        payload_data = kwargs.get("data", {})
        assert "language" not in payload_data
        
        # Call with "zh-CN"
        mock_post.reset_mock()
        res = src.transcriber.transcribe_groq("dummy.wav", "zh-CN")
        assert res is not None
        assert mock_post.called
        args, kwargs = mock_post.call_args
        payload_data = kwargs.get("data", {})
        assert payload_data.get("language") == "zh"
    finally:
        config.GROQ_API_KEY = old_key


def test_subtitle_only_validator_rules():
    from src.translation_validator import validate_translation
    
    # 1. Test TIMING_OVERFLOW bypass in subtitle_only mode
    segments = [
        {
            "id": 1,
            "text": "Hello",
            "start": 0.0,
            "end": 0.5,
            "duration": 0.5,
            "text_vi": "Đây là một câu rất dài có tốc độ đọc cao hơn mười lăm ký tự trên giây",
            "speaker": "SPEAKER_00",
            "speaker_gender": "male"
        }
    ]
    
    # In dub_audio (default) mode, this should flag a TIMING_OVERFLOW warning
    report_dub = validate_translation(segments, mode="dub_audio")
    timing_issues_dub = [iss for iss in report_dub["issues"] if iss["type"] == "TIMING_OVERFLOW"]
    assert len(timing_issues_dub) == 1
    
    # In subtitle_only mode, it should bypass it
    report_sub = validate_translation(segments, mode="subtitle_only")
    timing_issues_sub = [iss for iss in report_sub["issues"] if iss["type"] == "TIMING_OVERFLOW"]
    assert len(timing_issues_sub) == 0
    
    # 2. Test untranslated text detection
    untranslated_segments = [
        {
            "id": 2,
            "text": "Hello world",
            "start": 0.0,
            "end": 2.0,
            "duration": 2.0,
            "text_vi": "Hello world", # identical
            "speaker": "SPEAKER_00",
            "speaker_gender": "male"
        }
    ]
    report_untranslated = validate_translation(untranslated_segments, mode="subtitle_only")
    untranslated_issues = [iss for iss in report_untranslated["issues"] if iss["type"] == "UNTRANSLATED_TEXT"]
    assert len(untranslated_issues) == 1
    assert report_untranslated["bad_segments"] == 1

