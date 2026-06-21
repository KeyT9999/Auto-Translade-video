import json
import logging
import os
from unittest.mock import MagicMock

import pytest

import pipeline_vi


def test_subtitle_only_mode_execution(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    work_dir = tmp_path / "VN" / "test_session_vi"
    os.makedirs(work_dir, exist_ok=True)

    dummy_video_path = os.path.join(str(tmp_path), "dummy_video.mp4")
    with open(dummy_video_path, "w", encoding="utf-8") as f:
        f.write("mock video content")

    dummy_audio_path = os.path.join(str(work_dir), "original_audio.wav")
    with open(dummy_audio_path, "w", encoding="utf-8") as f:
        f.write("mock audio content")

    monkeypatch.setattr(pipeline_vi, "_resolve_video", lambda w, u, f: dummy_video_path)
    monkeypatch.setattr(pipeline_vi, "extract_audio", lambda v, a: None)
    monkeypatch.setattr(pipeline_vi.config, "GEMINI_ENABLED", False)
    monkeypatch.setattr(pipeline_vi.config, "GOOGLE_API_KEY", "")
    monkeypatch.setattr(pipeline_vi.config, "GROQ_API_KEY", "")

    mock_segments = [
        {"id": 1, "text": "Hello world", "start": 0.0, "end": 2.0, "duration": 2.0}
    ]
    monkeypatch.setattr(pipeline_vi, "transcribe", lambda a, l: mock_segments)

    mock_translated_segments = [
        {"id": 1, "text": "Hello world", "text_vi": "Xin chào thế giới", "start": 0.0, "end": 2.0, "duration": 2.0}
    ]

    import sys

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

    speaker_detection_called = False

    def mock_detect_speakers(segs):
        nonlocal speaker_detection_called
        speaker_detection_called = True
        return [dict(s, speaker="NARRATOR", speaker_gender="neutral") for s in segs]

    monkeypatch.setattr(pipeline_vi, "detect_speakers", mock_detect_speakers)

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

    burn_subtitles_called = False

    def mock_burn_subtitles(v, srt, o):
        nonlocal burn_subtitles_called
        burn_subtitles_called = True
        with open(o, "w", encoding="utf-8") as f:
            f.write("mock subtitled video")
        return o

    import src.video_merger

    monkeypatch.setattr(src.video_merger, "burn_subtitles_to_video", mock_burn_subtitles)

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
        mode="subtitle_only",
    )

    assert report["mode"] == "subtitle_only"
    assert not separate_vocals_called
    assert not speaker_detection_called
    assert not synthesize_called
    assert not merge_segments_called
    assert not merge_video_called
    assert burn_subtitles_called

    subtitled_video_path = os.path.join(report["output_dir"], "subtitled_video.mp4")
    assert report["files"]["dubbed_video"] == subtitled_video_path
    assert os.path.exists(subtitled_video_path)

    report_json_path = os.path.join(report["output_dir"], "report.json")
    assert os.path.exists(report_json_path)
    with open(report_json_path, encoding="utf-8") as f:
        saved_report = json.load(f)
    assert saved_report["mode"] == "subtitle_only"
    assert saved_report["files"]["audio_vi_full"] is None
    assert saved_report["files"]["dubbed_video"] == subtitled_video_path

    transcript_srt_path = os.path.join(report["output_dir"], "transcript_vi.srt")
    assert os.path.exists(transcript_srt_path)

    with open(saved_report["files"]["transcript_vi_json"], encoding="utf-8") as f:
        saved_segments = json.load(f)
    assert saved_segments[0]["text_vi"] == saved_segments[0]["subtitle_vi"]
    assert saved_segments[0]["text_vi"] == saved_segments[0]["dub_vi"]
    assert saved_segments[0]["text_vi"] == saved_segments[0]["final_dub_vi"]
    assert saved_segments[0]["speaker"] == "NARRATOR"
    assert saved_segments[0]["speaker_gender"] == "neutral"

    log_text = caplog.text
    assert "STEP 4.5: Detecting speakers" not in log_text
    assert "STEP 5: Synthesizing Vietnamese audio (LucyLab TTS)" not in log_text
    assert "STEP 6b: Fitting segments to timeline" not in log_text
    assert "STEP 6c: Merging audio segments" not in log_text


def test_subtitle_only_resume_rebuilds_srt_without_speaker_detection(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    work_dir = tmp_path / "VN" / "resume_session_vi"
    os.makedirs(work_dir, exist_ok=True)

    dummy_video_path = os.path.join(str(work_dir), "Douyin_sample.mp4")
    with open(dummy_video_path, "w", encoding="utf-8") as f:
        f.write("mock video content")

    with open(os.path.join(work_dir, "original_audio.wav"), "w", encoding="utf-8") as f:
        f.write("mock audio content")

    original_segments = [
        {"id": 1, "text": "你好", "start": 0.0, "end": 2.0, "duration": 2.0}
    ]
    translated_segments = [
        {"id": 1, "text": "你好", "text_vi": "Xin chào nhé", "start": 0.0, "end": 2.0, "duration": 2.0}
    ]

    with open(os.path.join(work_dir, "transcript_original.json"), "w", encoding="utf-8") as f:
        json.dump(original_segments, f, ensure_ascii=False, indent=2)
    with open(os.path.join(work_dir, "transcript_vi.json"), "w", encoding="utf-8") as f:
        json.dump(translated_segments, f, ensure_ascii=False, indent=2)

    monkeypatch.setattr(pipeline_vi, "extract_audio", lambda v, a: None)
    monkeypatch.setattr(pipeline_vi.config, "GEMINI_ENABLED", False)
    monkeypatch.setattr(pipeline_vi.config, "GOOGLE_API_KEY", "")
    monkeypatch.setattr(pipeline_vi.config, "GROQ_API_KEY", "")
    monkeypatch.setattr(pipeline_vi, "transcribe", lambda a, l: pytest.fail("ASR should not run on resume"))
    monkeypatch.setattr(pipeline_vi, "separate_vocals", lambda *a, **k: pytest.fail("Demucs should not run"))
    monkeypatch.setattr(pipeline_vi, "synthesize_segment_vi", lambda *a, **k: pytest.fail("TTS should not run"))
    monkeypatch.setattr(pipeline_vi, "merge_segments", lambda *a, **k: pytest.fail("Audio merge should not run"))
    monkeypatch.setattr(pipeline_vi, "merge_video", lambda *a, **k: pytest.fail("Dub merge should not run"))

    speaker_detection_called = False

    def mock_detect_speakers(segs):
        nonlocal speaker_detection_called
        speaker_detection_called = True
        return segs

    monkeypatch.setattr(pipeline_vi, "detect_speakers", mock_detect_speakers)

    import src.subtitle_renderer

    def mock_generate_ass(segments, output_path, style_config):
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("[Script Info]\n")
        return output_path

    def mock_render_with_cover(video_path, ass_path, output_path, cover_cfg):
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("mock subtitled video")
        return output_path

    monkeypatch.setattr(src.subtitle_renderer, "generate_ass_subtitles", mock_generate_ass)
    monkeypatch.setattr(src.subtitle_renderer, "render_video_with_cover", mock_render_with_cover)

    report = pipeline_vi.run_pipeline_vi(
        url=None,
        file_path=None,
        source_lang="zh-CN",
        voice_id="",
        skip_video=False,
        output_dir=str(tmp_path / "VN"),
        resume_dir=str(work_dir),
        burn_subtitles=True,
        mode="subtitle_only",
    )

    assert report["mode"] == "subtitle_only"
    assert not speaker_detection_called
    assert os.path.exists(os.path.join(work_dir, "transcript_vi.srt"))
    assert os.path.exists(os.path.join(work_dir, "transcript_vi.ass"))
    assert os.path.exists(os.path.join(work_dir, "subtitled_video.mp4"))

    with open(os.path.join(work_dir, "transcript_vi.srt"), encoding="utf-8") as f:
        srt_content = f.read()
    assert "Xin chào nhé" in srt_content

    with open(os.path.join(work_dir, "transcript_vi.json"), encoding="utf-8") as f:
        saved_segments = json.load(f)
    assert saved_segments[0]["text_vi"] == "Xin chào nhé"
    assert saved_segments[0]["subtitle_vi"] == "Xin chào nhé"
    assert saved_segments[0]["dub_vi"] == "Xin chào nhé"
    assert saved_segments[0]["final_dub_vi"] == "Xin chào nhé"
    assert saved_segments[0]["speaker"] == "NARRATOR"
    assert saved_segments[0]["speaker_gender"] == "neutral"

    log_text = caplog.text
    assert "STEP 4.5: Detecting speakers" not in log_text
    assert "STEP 5: Synthesizing Vietnamese audio (LucyLab TTS)" not in log_text
    assert "STEP 6c: Merging audio segments" not in log_text


def test_transcribe_auto_language(monkeypatch):
    import requests
    import src.transcriber

    mock_post = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"segments": [{"start": 0.0, "end": 2.0, "text": "Test"}]}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(os.path, "exists", lambda x: True)

    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MagicMock(returncode=0))

    import builtins

    mock_open_instance = MagicMock()
    mock_open = MagicMock(return_value=mock_open_instance)
    monkeypatch.setattr(builtins, "open", mock_open)

    import config

    old_key = config.GROQ_API_KEY
    config.GROQ_API_KEY = "mock_key"

    try:
        res = src.transcriber.transcribe_groq("dummy.wav", "auto")
        assert res is not None
        assert mock_post.called
        args, kwargs = mock_post.call_args
        payload_data = kwargs.get("data", {})
        assert "language" not in payload_data

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

    segments = [
        {
            "id": 1,
            "text": "This source text is intentionally long enough to avoid hallucination detection",
            "start": 0.0,
            "end": 0.5,
            "duration": 0.5,
            "text_vi": "Câu này vẫn quá dài so với nửa giây.",
            "speaker": "SPEAKER_00",
            "speaker_gender": "male",
        }
    ]

    report_dub = validate_translation(segments, mode="dub_audio")
    timing_issues_dub = [iss for iss in report_dub["issues"] if iss["type"] == "TIMING_OVERFLOW"]
    assert len(timing_issues_dub) == 1

    report_sub = validate_translation(segments, mode="subtitle_only")
    timing_issues_sub = [iss for iss in report_sub["issues"] if iss["type"] == "TIMING_OVERFLOW"]
    assert len(timing_issues_sub) == 1
    assert timing_issues_sub[0]["severity"] == "warning"
    assert report_sub["bad_segments"] == 0

    untranslated_segments = [
        {
            "id": 2,
            "text": "Hello world",
            "start": 0.0,
            "end": 2.0,
            "duration": 2.0,
            "text_vi": "Hello world",
            "speaker": "SPEAKER_00",
            "speaker_gender": "male",
        }
    ]
    report_untranslated = validate_translation(untranslated_segments, mode="subtitle_only")
    untranslated_issues = [iss for iss in report_untranslated["issues"] if iss["type"] == "UNTRANSLATED_TEXT"]
    assert len(untranslated_issues) == 1
    assert report_untranslated["bad_segments"] == 1


def test_validator_does_not_false_positive_short_cjk_dialogue():
    from src.translation_validator import validate_translation

    segments = [
        {
            "id": 1,
            "text": "你可算来了",
            "start": 0.0,
            "end": 2.46,
            "duration": 2.46,
            "text_vi": "Cậu đến rồi à.",
            "speaker": "NARRATOR",
            "speaker_gender": "neutral",
        }
    ]

    report = validate_translation(segments, mode="subtitle_only")
    hallucination_issues = [
        iss for iss in report["issues"] if iss["type"] in {"TRUE_HALLUCINATION", "LENGTH_RATIO_WARNING"}
    ]
    assert hallucination_issues == []
    assert report["bad_segments"] == 0


def test_ass_subtitle_generation(tmp_path):
    from src.subtitle_renderer import generate_ass_subtitles

    segments = [
        {"id": 1, "text_vi": "Xin chào thế giới", "start": 1.0, "end": 3.5}
    ]

    ass_path_boxed = os.path.join(str(tmp_path), "sub_boxed.ass")
    generate_ass_subtitles(
        segments,
        ass_path_boxed,
        {
            "style": "boxed",
            "font_name": "Courier New",
            "font_size": 52,
            "box_opacity": 0.75,
        },
    )

    assert os.path.exists(ass_path_boxed)
    with open(ass_path_boxed, encoding="utf-8-sig") as f:
        content_boxed = f.read()

    assert "Style: VietSub,Courier New,52" in content_boxed
    assert "BorderStyle, Outline, Shadow" in content_boxed
    assert "4,2,1" in content_boxed or "BorderStyle, Outline, Shadow" in content_boxed
    assert "&H3F000000" in content_boxed
    assert "Dialogue: 0,0:00:01.00,0:00:03.50,VietSub,,0,0,0,,Xin chào thế giới" in content_boxed

    ass_path_plain = os.path.join(str(tmp_path), "sub_plain.ass")
    generate_ass_subtitles(
        segments,
        ass_path_plain,
        {
            "style": "plain",
            "font_name": "Arial",
            "font_size": 40,
        },
    )

    assert os.path.exists(ass_path_plain)
    with open(ass_path_plain, encoding="utf-8-sig") as f:
        content_plain = f.read()

    assert "Style: VietSub,Arial,40" in content_plain
    assert "&H80000000" in content_plain
    assert "Dialogue: 0,0:00:01.00,0:00:03.50,VietSub,,0,0,0,,Xin chào thế giới" in content_plain
