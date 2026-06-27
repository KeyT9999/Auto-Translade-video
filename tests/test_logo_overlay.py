import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from src.subtitle_renderer import render_video_with_cover
from src.video_merger import merge_video

def test_render_video_with_cover_logo_overlay(tmp_path):
    video_path = tmp_path / "test_video.mp4"
    video_path.write_text("fake video data")
    ass_path = tmp_path / "subtitles.ass"
    ass_path.write_text("fake ass data")
    logo_path = tmp_path / "logo.png"
    logo_path.write_text("fake logo data")
    output_path = tmp_path / "output.mp4"

    logo_config = {
        "logo_path": str(logo_path),
        "logo_position": "top_left",
        "logo_width": 120
    }

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        render_video_with_cover(
            input_video=str(video_path),
            ass_path=str(ass_path),
            output_path=str(output_path),
            cover_config={"cover_original_subtitles": False},
            logo_config=logo_config
        )

        assert mock_run.called
        args = mock_run.call_args[0][0]
        # Should be using -filter_complex
        assert "-filter_complex" in args
        # Check scale and overlay positions
        filter_str = args[args.index("-filter_complex") + 1]
        assert "scale=120:-1" in filter_str
        assert "overlay=10:10" in filter_str
        assert str(logo_path) in args

def test_merge_video_logo_overlay(tmp_path):
    video_path = tmp_path / "test_video.mp4"
    video_path.write_text("fake video data")
    audio_path = tmp_path / "test_audio.wav"
    audio_path.write_text("fake audio data")
    logo_path = tmp_path / "logo.png"
    logo_path.write_text("fake logo data")
    output_path = tmp_path / "output.mp4"

    logo_config = {
        "logo_path": str(logo_path),
        "logo_position": "bottom_right",
        "logo_width": 200
    }

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        merge_video(
            video_path=str(video_path),
            audio_path=str(audio_path),
            output_path=str(output_path),
            srt_path=None,
            cover_config=None,
            logo_config=logo_config
        )

        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert "-filter_complex" in args
        filter_str = args[args.index("-filter_complex") + 1]
        assert "scale=200:-1" in filter_str
        assert "overlay=main_w-overlay_w-10:main_h-overlay_h-10" in filter_str
