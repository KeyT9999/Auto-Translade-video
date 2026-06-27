import json
import logging
import os
from unittest.mock import MagicMock

import pytest

import pipeline_vi


def test_subtitle_timing_sync_in_dub_audio_mode(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    work_dir = tmp_path / "VN" / "test_session_vi"
    os.makedirs(work_dir, exist_ok=True)

    dummy_video_path = os.path.join(str(tmp_path), "dummy_video.mp4")
    with open(dummy_video_path, "w", encoding="utf-8") as f:
        f.write("mock video content")

    dummy_audio_path = os.path.join(str(work_dir), "original_audio.wav")
    with open(dummy_audio_path, "w", encoding="utf-8") as f:
        f.write("mock audio content")

    # Mock video and audio operations
    monkeypatch.setattr(pipeline_vi, "_resolve_video", lambda w, u, f: dummy_video_path)
    monkeypatch.setattr(pipeline_vi, "extract_audio", lambda v, a: None)
    monkeypatch.setattr(pipeline_vi.config, "GEMINI_ENABLED", False)
    monkeypatch.setattr(pipeline_vi.config, "GOOGLE_API_KEY", "")
    monkeypatch.setattr(pipeline_vi.config, "GROQ_API_KEY", "")
    monkeypatch.setattr(pipeline_vi.config, "SUBTITLE_SILENT_PADDING", 0.5)

    mock_segments = [
        {"id": 1, "text": "Hello world", "start": 0.0, "end": 2.0, "duration": 2.0}
    ]
    monkeypatch.setattr(pipeline_vi, "transcribe", lambda a, l: mock_segments)

    mock_translated_segments = [
        {"id": 1, "text": "Hello world", "text_vi": "Xin chào thế giới", "start": 0.0, "end": 2.0, "duration": 2.0}
    ]

    import sys

    # Mock translation services
    mock_context_builder = MagicMock()
    mock_context_builder.build_video_context.return_value = {"translation_style": "spoken Vietnamese"}
    monkeypatch.setitem(sys.modules, "src.context_builder", mock_context_builder)

    mock_glossary_builder = MagicMock()
    mock_glossary_builder.build_glossary.return_value = {"terms": {}}
    monkeypatch.setitem(sys.modules, "src.glossary_builder", mock_glossary_builder)

    mock_character_profiler = MagicMock()
    mock_character_profiler.build_character_bible.return_value = {"characters": []}
    monkeypatch.setitem(sys.modules, "src.character_profiler", mock_character_profiler)

    mock_translator_module = MagicMock()
    mock_translator_module.translate_segments_contextual.return_value = mock_translated_segments
    monkeypatch.setitem(sys.modules, "src.contextual_translator", mock_translator_module)

    mock_validator_module = MagicMock()
    mock_validator_module.validate_translation.return_value = {"bad_segments": 0, "issues": []}
    mock_validator_module.filter_repairable_issues.return_value = []
    mock_validator_module.has_blocking_errors.return_value = False
    monkeypatch.setitem(sys.modules, "src.translation_validator", mock_validator_module)

    mock_glossary_enforcer = MagicMock()
    mock_glossary_enforcer.apply_glossary_to_segments.side_effect = lambda segs, glossary=None: segs
    monkeypatch.setitem(sys.modules, "src.glossary_enforcer", mock_glossary_enforcer)

    mock_subtitle_group_rewriter = MagicMock()
    mock_subtitle_group_rewriter.rewrite_subtitle_groups.side_effect = lambda segs: segs
    monkeypatch.setitem(sys.modules, "src.subtitle_group_rewriter", mock_subtitle_group_rewriter)

    mock_rewriter_module = MagicMock()
    mock_rewriter_module.rewrite_timeline.return_value = mock_translated_segments
    monkeypatch.setitem(sys.modules, "src.timeline_rewriter", mock_rewriter_module)

    # Mock Speaker Detection
    monkeypatch.setattr(pipeline_vi, "detect_speakers", lambda segs: [
        dict(s, speaker="NARRATOR", speaker_gender="neutral") for s in segs
    ])

    # Mock Vocal Separation
    monkeypatch.setattr(pipeline_vi, "separate_vocals", lambda a, w: {"no_vocals": None})

    def mock_synthesize(text_vi, output_path, target_duration, voice_id):
        from pydub.generators import Sine
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        Sine(440).to_audio_segment(duration=1500).export(output_path, format="wav")
        return {
            "path": output_path,
            "actual_duration": 1.5,
            "speed_adjusted": False,
            "rate_applied": "1.0x",
            "provider": "lucylab",
            "voice_id": voice_id,
            "status": "generated",
        }
    monkeypatch.setattr(pipeline_vi, "synthesize_segment_vi", mock_synthesize)

    # Mock Audio Merger fitting tool
    # Returns 'after' = 1.5s
    monkeypatch.setattr(pipeline_vi, "fit_segments_to_timeline", lambda segs, src, dst: [
        {
            "id": 1,
            "available": 2.0,
            "before": 1.5,
            "after": 1.5,
            "speed": 1.0,
            "status": "OK",
        }
    ])

    # Mock audio merge and video overlay
    monkeypatch.setattr(pipeline_vi, "merge_segments", lambda *args, **kwargs: "mock_merged_audio.wav")
    monkeypatch.setattr(pipeline_vi, "merge_video", lambda *args, **kwargs: None)

    # Mock file checks to check existence
    monkeypatch.setattr(pipeline_vi, "is_valid_audio_file", lambda path: os.path.exists(path))

    import src.subtitle_renderer
    monkeypatch.setattr(src.subtitle_renderer, "generate_ass_subtitles", lambda segs, path, style, **kwargs: path)
    monkeypatch.setattr(src.subtitle_renderer, "render_video_with_cover", lambda *args: "mock_subtitled_video.mp4")

    # Run the pipeline in dub_audio mode (subtitle_mode is False)
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
        mode="dub_audio",
    )

    # Load transcript_vi.json
    transcript_vi_path = report["files"]["transcript_vi_json"]
    assert os.path.exists(transcript_vi_path)
    with open(transcript_vi_path, encoding="utf-8") as f:
        saved_segments = json.load(f)

    # Validate that end time has been adjusted correctly
    # start (0.0) + max(0.1, after (1.5) - padding (0.5)) = 1.0
    assert saved_segments[0]["end"] == 1.0

    # Validate transcript_vi.srt has also been regenerated with the updated timing (1.0)
    transcript_vi_srt = report["files"]["transcript_vi_srt"]
    assert os.path.exists(transcript_vi_srt)
    with open(transcript_vi_srt, encoding="utf-8") as f:
        srt_content = f.read()

    assert "00:00:00,000 --> 00:00:01,000" in srt_content
