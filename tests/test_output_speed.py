import os
import json
import pytest
import subprocess
from src.output_speed import (
    validate_output_speed,
    build_speed_suffix,
    adjust_srt_for_speed,
    adjust_ass_for_speed,
    adjust_transcript_json_for_speed,
    apply_playback_speed_to_video,
)

def test_validate_output_speed():
    # Valid
    assert validate_output_speed(1.0) == 1.0
    assert validate_output_speed(1.1) == 1.1
    assert validate_output_speed(1.2) == 1.2
    assert validate_output_speed(1.3) == 1.3
    assert validate_output_speed("1.2") == 1.2

    # Invalid
    with pytest.raises(ValueError):
        validate_output_speed(1.5)
    with pytest.raises(ValueError):
        validate_output_speed(0.0)
    with pytest.raises(ValueError):
        validate_output_speed(-1.0)
    with pytest.raises(ValueError):
        validate_output_speed("abc")

def test_build_speed_suffix():
    assert build_speed_suffix(1.0) == ""
    assert build_speed_suffix(1.2) == "_1.2x"

def test_adjust_srt_for_speed(tmp_path):
    input_srt = tmp_path / "test.srt"
    output_srt = tmp_path / "test_out.srt"

    srt_content = (
        "1\n"
        "00:00:10,000 --> 00:00:15,000\n"
        "Xin chào\n"
        "\n"
        "2\n"
        "00:01:00,000 --> 00:01:30,000\n"
        "Tạm biệt\n"
    )
    input_srt.write_text(srt_content, encoding="utf-8")

    # Speed 1.2
    # 10s / 1.2 = 8.333s -> 00:00:08,333
    # 15s / 1.2 = 12.5s -> 00:00:12,500
    # 60s / 1.2 = 50s -> 00:00:50,000
    # 90s / 1.2 = 75s -> 00:01:15,000
    adjust_srt_for_speed(str(input_srt), str(output_srt), 1.2)

    output_content = output_srt.read_text(encoding="utf-8")
    assert "00:00:08,333 --> 00:00:12,500" in output_content
    assert "00:00:50,000 --> 00:01:15,000" in output_content
    assert "Xin chào" in output_content
    assert "Tạm biệt" in output_content

def test_adjust_ass_for_speed(tmp_path):
    input_ass = tmp_path / "test.ass"
    output_ass = tmp_path / "test_out.ass"

    ass_content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:10.00,0:00:15.00,Default,,0,0,0,,Xin chào\n"
    )
    input_ass.write_text(ass_content, encoding="utf-8-sig")

    # Speed 1.2
    # 10s / 1.2 = 8.333s -> 0:00:08.33
    # 15s / 1.2 = 12.5s -> 0:00:12.50
    adjust_ass_for_speed(str(input_ass), str(output_ass), 1.2)

    output_content = output_ass.read_text(encoding="utf-8-sig")
    assert "Dialogue: 0,0:00:08.33,0:00:12.50,Default" in output_content
    assert "Xin chào" in output_content

def test_adjust_transcript_json_for_speed(tmp_path):
    input_json = tmp_path / "transcript.json"
    output_json = tmp_path / "transcript_out.json"

    data = [
        {"id": 1, "start": 10.0, "end": 15.0, "duration": 5.0, "text": "Xin chào"},
        {"id": 2, "start": 60.0, "end": 90.0, "duration": 30.0, "text": "Tạm biệt"}
    ]
    with open(input_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    adjust_transcript_json_for_speed(str(input_json), str(output_json), 1.2)

    with open(output_json, "r", encoding="utf-8") as f:
        out_data = json.load(f)

    assert out_data[0]["start"] == 8.333
    assert out_data[0]["end"] == 12.5
    assert out_data[0]["duration"] == 4.167
    assert out_data[1]["start"] == 50.0
    assert out_data[1]["end"] == 75.0
    assert out_data[1]["duration"] == 25.0

def test_apply_playback_speed_to_video_ffmpeg_command(monkeypatch, tmp_path):
    input_video = tmp_path / "input.mp4"
    output_video = tmp_path / "output.mp4"
    input_video.write_text("dummy video content")

    has_audio_called = False
    def mock_has_audio(video_path):
        nonlocal has_audio_called
        has_audio_called = True
        return True

    import src.output_speed
    monkeypatch.setattr(src.output_speed, "_has_audio_stream", mock_has_audio)

    subprocess_run_called = False
    def mock_run(cmd, stdout=None, stderr=None, text=True):
        nonlocal subprocess_run_called
        subprocess_run_called = True
        
        # Verify ffmpeg arguments
        assert "ffmpeg" in cmd[0]
        assert "-filter_complex" in cmd
        filter_idx = cmd.index("-filter_complex")
        filter_val = cmd[filter_idx + 1]
        assert "setpts=PTS/1.2" in filter_val
        assert "atempo=1.2" in filter_val
        
        class MockCompletedProcess:
            returncode = 0
            stdout = ""
            stderr = ""
        return MockCompletedProcess()

    monkeypatch.setattr(subprocess, "run", mock_run)

    apply_playback_speed_to_video(str(input_video), str(output_video), 1.2)

    assert has_audio_called is True
    assert subprocess_run_called is True
