import os
import subprocess
from src.utils import setup_logging

logger = setup_logging("video_merger")


def merge_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    srt_path: str | None = None,
    cover_config: dict | None = None,
) -> str:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    if srt_path and os.path.exists(srt_path):
        from src.subtitle_renderer import _build_video_filter_chain, _escape_ffmpeg_path, _build_cover_filters
        
        # Build filter chain depending on whether it is .ass or .srt
        if srt_path.lower().endswith(".ass"):
            vf_string = _build_video_filter_chain(srt_path, cover_config)
        else:
            srt_escaped = _escape_ffmpeg_path(os.path.abspath(srt_path))
            filters = _build_cover_filters(cover_config)
            filters.append(f"subtitles='{srt_escaped}'")
            vf_string = ",".join(filters)

        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", audio_path,
            "-vf", vf_string,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-map", "0:v",
            "-map", "1:a",
            "-shortest",
            "-y",
            output_path,
        ]
        logger.info(f"Merging video + audio + burning subtitles/cover ({srt_path}) → {output_path}")
    else:
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-map", "0:v",
            "-map", "1:a",
            "-shortest",
            "-y",
            output_path,
        ]
        logger.info(f"Merging video + audio (copy stream) → {output_path}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg merge failed: {result.stderr}")

    logger.info(f"Video merged: {output_path}")
    return output_path


def burn_subtitles_to_video(video_path: str, srt_path: str, output_path: str) -> str:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"Subtitles not found: {srt_path}")

    # Convert path to relative and use forward slashes for FFmpeg subtitles filter on Windows
    srt_rel = os.path.relpath(srt_path).replace("\\", "/")
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", f"subtitles={srt_rel}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-c:a", "copy",
        "-y",
        output_path,
    ]
    logger.info(f"Burning subtitles ({srt_rel}) onto {video_path} → {output_path}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Retry with aac audio encoding if copy fails
        logger.warning(f"FFmpeg copy audio failed, retrying with aac re-encoding...")
        cmd[cmd.index("copy")] = "aac"
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg subtitles burn failed: {result.stderr}")

    logger.info(f"Subtitles burned: {output_path}")
    return output_path
