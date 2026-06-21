import logging
import os
import sys
from unittest.mock import MagicMock

import pipeline_vi


def test_warning_only_quality_does_not_trigger_legacy_fallback(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    work_dir = tmp_path / "VN" / "warning_only_vi"
    os.makedirs(work_dir, exist_ok=True)

    dummy_video_path = os.path.join(str(tmp_path), "dummy_video.mp4")
    with open(dummy_video_path, "w", encoding="utf-8") as handle:
        handle.write("mock video content")

    dummy_audio_path = os.path.join(str(work_dir), "original_audio.wav")
    with open(dummy_audio_path, "w", encoding="utf-8") as handle:
        handle.write("mock audio content")

    monkeypatch.setattr(pipeline_vi, "_resolve_video", lambda w, u, f: dummy_video_path)
    monkeypatch.setattr(pipeline_vi, "extract_audio", lambda v, a: None)
    monkeypatch.setattr(pipeline_vi.config, "GEMINI_ENABLED", False)
    monkeypatch.setattr(pipeline_vi.config, "GOOGLE_API_KEY", "")
    monkeypatch.setattr(pipeline_vi.config, "GROQ_API_KEY", "")

    source_segments = [
        {
            "id": 1,
            "text": "\u8fd9\u5c31\u662f\u4f20\u8bf4\u4e2d",
            "start": 0.0,
            "end": 2.0,
            "duration": 2.0,
        }
    ]
    monkeypatch.setattr(pipeline_vi, "transcribe", lambda a, l: source_segments)

    translated_segments = [
        {
            "id": 1,
            "text": "\u8fd9\u5c31\u662f\u4f20\u8bf4\u4e2d",
            "text_vi": "\u0110\u00e2y ch\u00ednh l\u00e0 thuy\u1ec1n bay n\u1ed5i ti\u1ebfng trong truy\u1ec1n thuy\u1ebft.",
            "start": 0.0,
            "end": 2.0,
            "duration": 2.0,
        }
    ]

    mock_context_builder = MagicMock()
    mock_context_builder.build_video_context.return_value = {"translation_style": "spoken Vietnamese"}
    monkeypatch.setitem(sys.modules, "src.context_builder", mock_context_builder)

    mock_glossary_builder = MagicMock()
    mock_glossary_builder.build_glossary.return_value = {"terms": {"\u98de\u5929\u753b\u823b": "thuy\u1ec1n bay"}}
    monkeypatch.setitem(sys.modules, "src.glossary_builder", mock_glossary_builder)

    mock_character_profiler = MagicMock()
    mock_character_profiler.build_character_bible.return_value = {"characters": []}
    monkeypatch.setitem(sys.modules, "src.character_profiler", mock_character_profiler)

    mock_contextual_translator = MagicMock()
    mock_contextual_translator.translate_segments_contextual.return_value = translated_segments
    monkeypatch.setitem(sys.modules, "src.contextual_translator", mock_contextual_translator)

    legacy_called = False

    def mock_legacy_translate(*args, **kwargs):
        nonlocal legacy_called
        legacy_called = True
        return translated_segments

    mock_legacy_translator = MagicMock()
    mock_legacy_translator.translate_segments = mock_legacy_translate
    monkeypatch.setitem(sys.modules, "src.translator", mock_legacy_translator)

    monkeypatch.setattr(pipeline_vi, "detect_speakers", lambda segs: segs)
    monkeypatch.setattr(pipeline_vi, "separate_vocals", lambda *a, **k: {"no_vocals": None})
    monkeypatch.setattr(pipeline_vi, "synthesize_segment_vi", lambda *a, **k: None)
    monkeypatch.setattr(pipeline_vi, "merge_segments", lambda *a, **k: None)
    monkeypatch.setattr(pipeline_vi, "merge_video", lambda *a, **k: None)

    def mock_burn_subtitles(video_path, srt_path, output_path):
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write("mock subtitled video")
        return output_path

    import src.video_merger

    monkeypatch.setattr(src.video_merger, "burn_subtitles_to_video", mock_burn_subtitles)

    report = pipeline_vi.run_pipeline_vi(
        url=None,
        file_path="mock_file.mp4",
        source_lang="zh-CN",
        voice_id="",
        skip_video=False,
        output_dir=str(tmp_path / "VN"),
        resume_dir=None,
        burn_subtitles=True,
        mode="subtitle_only",
    )

    assert report["mode"] == "subtitle_only"
    assert not legacy_called
    assert os.path.exists(os.path.join(report["output_dir"], "transcript_vi.srt"))
    assert os.path.exists(os.path.join(report["output_dir"], "subtitled_video.mp4"))

    quality_report_path = os.path.join(report["output_dir"], "translation_quality_report.json")
    assert os.path.exists(quality_report_path)

    log_text = caplog.text
    assert "Falling back to old translation after contextual QA failure" not in log_text
