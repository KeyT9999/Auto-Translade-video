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
    logo_config: dict | None = None,
) -> str:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    logo_path = logo_config.get("logo_path") if logo_config else None
    has_logo = logo_path and os.path.exists(logo_path)

    if (srt_path and os.path.exists(srt_path)) or has_logo:
        from src.subtitle_renderer import _escape_ffmpeg_path, _build_cover_filters
        
        # Build filter complex
        filter_nodes = []
        sub_filters = []
        if srt_path and os.path.exists(srt_path):
            if srt_path.lower().endswith(".ass"):
                sub_filters.extend(_build_cover_filters(cover_config))
                ass_escaped = _escape_ffmpeg_path(os.path.abspath(srt_path))
                sub_filters.append(f"ass='{ass_escaped}'")
            else:
                srt_escaped = _escape_ffmpeg_path(os.path.abspath(srt_path))
                sub_filters.extend(_build_cover_filters(cover_config))
                sub_filters.append(f"subtitles='{srt_escaped}'")

        if sub_filters:
            filter_nodes.append(f"[0:v]{','.join(sub_filters)}[v_base]")
            base_video_label = "[v_base]"
        else:
            base_video_label = "[0:v]"

        if has_logo:
            logo_width = logo_config.get("logo_width")
            logo_position = logo_config.get("logo_position", "top_right")

            # Map position to expression
            if logo_position in ("top_left", "top-left"):
                pos_expr = "10:10"
            elif logo_position in ("bottom_left", "bottom-left"):
                pos_expr = "10:main_h-overlay_h-10"
            elif logo_position in ("bottom_right", "bottom-right"):
                pos_expr = "main_w-overlay_w-10:main_h-overlay_h-10"
            else:
                pos_expr = "main_w-overlay_w-10:10"

            if logo_width:
                filter_nodes.append(f"[2:v]scale={logo_width}:-1[v_logo]")
            else:
                filter_nodes.append(f"[2:v]null[v_logo]")

            filter_nodes.append(f"{base_video_label}[v_logo]overlay={pos_expr}[v_out]")
            final_video_label = "[v_out]"
        else:
            final_video_label = base_video_label

        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", audio_path,
        ]
        if has_logo:
            cmd.extend(["-i", logo_path])

        cmd.extend([
            "-filter_complex", ";".join(filter_nodes),
            "-map", final_video_label,
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-shortest",
            "-y",
            output_path,
        ])
        logger.info(f"Merging video + audio + overlaying cover/subtitles/logo → {output_path}")
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
    try:
        srt_rel = os.path.relpath(srt_path).replace("\\", "/")
    except ValueError:
        from src.subtitle_renderer import _escape_ffmpeg_path
        srt_rel = _escape_ffmpeg_path(os.path.abspath(srt_path))
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
