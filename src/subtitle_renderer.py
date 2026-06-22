"""Subtitle Renderer — Generates ASS subtitles and renders video with subtitle cover overlay.

Supports two subtitle styles:
  - 'plain': White text with black outline and shadow (BorderStyle=1)
  - 'boxed': White text on a semi-transparent dark background box (BorderStyle=4)

When cover_original_subtitles is enabled, a dark drawbox overlay is rendered
over the original subtitle region before the Vietnamese ASS subtitles are composited.
"""
import os
import subprocess
import config
from src.subtitle_formatter import split_timed_subtitle_chunks
from src.utils import setup_logging

logger = setup_logging("subtitle_renderer")

# Field priority for resolving Vietnamese subtitle text
SUBTITLE_TEXT_FIELDS = ["subtitle_vi", "final_dub_vi", "dub_vi", "text_vi", "literal_vi"]


def _resolve_subtitle_text(segment: dict) -> str:
    """Pick the best available Vietnamese text from a segment using field priority."""
    for field in SUBTITLE_TEXT_FIELDS:
        val = segment.get(field)
        if val and str(val).strip():
            return str(val).strip()
    return ""


def _wrap_text(text: str, max_chars_per_line: int = 24) -> str:
    """Wrap text to at most 2 lines using ASS newline (\\N).

    Splits at word boundaries and preserves Vietnamese diacritics.
    """
    import re
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars_per_line:
        return text

    words = text.split(" ")
    lines: list[str] = []
    current_line: list[str] = []

    for word in words:
        candidate = " ".join(current_line + [word])
        if len(candidate) <= max_chars_per_line:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    # Keep at most 2 lines, join with ASS newline
    return "\\N".join(lines[:2])


def _build_cover_filters(cover_config: dict | None = None) -> list[str]:
    cfg = cover_config or {}
    if not cfg.get("cover_original_subtitles", False):
        return []

    mask_y = cfg.get("mask_y_percent", config.SUBTITLE_MASK_Y_PERCENT)
    mask_h = cfg.get("mask_height_percent", config.SUBTITLE_MASK_HEIGHT_PERCENT)
    mask_opacity = cfg.get("mask_opacity", config.SUBTITLE_MASK_OPACITY)
    extra_h = cfg.get("mask_extra_height_percent", config.SUBTITLE_MASK_EXTRA_HEIGHT_PERCENT)
    extra_opacity = cfg.get("mask_extra_opacity", config.SUBTITLE_MASK_EXTRA_OPACITY)

    filters = [
        (
            f"drawbox=x=0:y=ih*{mask_y}:w=iw:h=ih*{mask_h}"
            f":color=black@{mask_opacity}:t=fill"
        )
    ]
    if extra_h > 0:
        extra_y = max(mask_y - extra_h, 0.0)
        filters.append(
            (
                f"drawbox=x=0:y=ih*{extra_y}:w=iw:h=ih*{extra_h}"
                f":color=black@{extra_opacity}:t=fill"
            )
        )
    return filters


def _build_video_filter_chain(ass_path: str, cover_config: dict | None = None) -> str:
    ass_escaped = _escape_ffmpeg_path(os.path.abspath(ass_path))
    filters = _build_cover_filters(cover_config)
    filters.append(f"ass='{ass_escaped}'")
    return ",".join(filters)


def _format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cc (centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_ass_subtitles(
    segments: list[dict],
    output_path: str,
    style_config: dict | None = None,
) -> str:
    """Generate an ASS subtitle file from translated segments.

    Args:
        segments: List of segment dicts with Vietnamese text fields.
        output_path: Path to write the .ass file.
        style_config: Optional dict with keys:
            - style: 'boxed' or 'plain' (default 'plain')
            - font_name, font_size, outline_size, shadow_size
            - box_opacity (0.0-1.0, for boxed style)
            - margin_bottom (pixels)
            - max_chars_per_line (int)

    Returns:
        Path to the generated .ass file.
    """
    cfg = style_config or {}
    style = cfg.get("style", "plain")
    font_name = cfg.get("font_name", config.SUBTITLE_FONT_NAME)
    font_size = cfg.get("font_size", config.SUBTITLE_FONT_SIZE)
    outline_size = cfg.get("outline_size", config.SUBTITLE_OUTLINE_SIZE)
    shadow_size = cfg.get("shadow_size", config.SUBTITLE_SHADOW_SIZE)
    box_opacity = cfg.get("box_opacity", config.SUBTITLE_BOX_OPACITY)
    margin_bottom = cfg.get("margin_bottom", config.SUBTITLE_MARGIN_BOTTOM)
    max_chars = cfg.get("max_chars_per_line", config.SUBTITLE_MAX_CHARS_PER_LINE)

    logger.info(f"Generating ASS subtitles (style={style}, segments={len(segments)})")

    # ASS colour format: &HAABBGGRR (alpha, blue, green, red)
    primary_colour = "&H00FFFFFF"       # White, fully opaque
    outline_colour = "&H00000000"       # Black, fully opaque
    secondary_colour = "&H000000FF"     # Red (unused, ASS convention)

    # BackColour alpha: 00=opaque, FF=transparent
    # Convert box_opacity (0.0=transparent, 1.0=opaque) to ASS alpha (hex)
    if style == "boxed":
        border_style = 4  # Opaque box
        alpha_value = int((1.0 - box_opacity) * 255)
        back_colour = f"&H{alpha_value:02X}000000"  # Semi-transparent black
    else:
        border_style = 1  # Outline + shadow
        back_colour = "&H80000000"  # Default semi-transparent for shadow

    # Build ASS content
    lines = []

    # [Script Info]
    lines.append("\ufeff[Script Info]")  # UTF-8 BOM
    lines.append("ScriptType: v4.00+")
    lines.append("Collisions: Normal")
    lines.append("PlayResX: 1080")
    lines.append("PlayResY: 1920")
    lines.append("Timer: 100.0000")
    lines.append("WrapStyle: 0")
    lines.append("")

    # [V4+ Styles]
    lines.append("[V4+ Styles]")
    lines.append(
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    style_line = (
        f"Style: VietSub,{font_name},{font_size},"
        f"{primary_colour},{secondary_colour},{outline_colour},{back_colour},"
        f"-1,0,0,0,"       # Bold=true, no italic/underline/strikeout
        f"100,100,0,0,"    # ScaleX,ScaleY,Spacing,Angle
        f"{border_style},{outline_size},{shadow_size},"
        f"2,"              # Alignment 2 = bottom-center
        f"20,20,{margin_bottom},"   # MarginL, MarginR, MarginV
        f"1"               # Encoding (1=Unicode default)
    )
    lines.append(style_line)
    lines.append("")

    # [Events]
    lines.append("[Events]")
    lines.append(
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    )

    dialogue_count = 0
    for seg in segments:
        text = _resolve_subtitle_text(seg)
        if not text:
            continue

        timed_chunks = split_timed_subtitle_chunks(
            seg.get("start", 0.0),
            seg.get("end", 0.0),
            text,
            max_chars_per_line=max_chars,
            max_lines_per_chunk=2,
        )

        for chunk_start, chunk_end, chunk_text in timed_chunks:
            start = _format_ass_time(chunk_start)
            end = _format_ass_time(chunk_end)
            wrapped = _wrap_text(chunk_text, max_chars)
            lines.append(f"Dialogue: 0,{start},{end},VietSub,,0,0,0,,{wrapped}")
            dialogue_count += 1

    # Write file
    content = "\n".join(lines) + "\n"
    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write(content)

    logger.info(f"ASS subtitles written: {output_path} ({dialogue_count} dialogue entries)")
    return output_path


def _escape_ffmpeg_path(path: str) -> str:
    """Escape a file path for use inside FFmpeg filter expressions on Windows.

    FFmpeg filter syntax requires colons and backslashes to be escaped.
    """
    # Use forward slashes
    escaped = path.replace("\\", "/")
    # Escape colons (e.g. C: → C\\:) and single quotes
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("'", "\\'")
    return escaped


def render_video_with_cover(
    input_video: str,
    ass_path: str,
    output_path: str,
    cover_config: dict | None = None,
) -> str:
    """Render video with optional subtitle cover overlay and ASS subtitles.

    Args:
        input_video: Path to input video file.
        ass_path: Path to ASS subtitle file.
        output_path: Path for the output video.
        cover_config: Optional dict with keys:
            - cover_original_subtitles: bool (default False)
            - mask_y_percent: float (0.0-1.0, default from config)
            - mask_height_percent: float (0.0-1.0, default from config)
            - mask_opacity: float (0.0-1.0, default from config)

    Returns:
        Path to the rendered output video.
    """
    if not os.path.exists(input_video):
        raise FileNotFoundError(f"Video not found: {input_video}")
    if not os.path.exists(ass_path):
        raise FileNotFoundError(f"ASS subtitles not found: {ass_path}")

    cfg = cover_config or {}
    vf_string = _build_video_filter_chain(ass_path, cfg)
    if cfg.get("cover_original_subtitles", False):
        logger.info(
            "Applying subtitle cover: y=%.0f%% h=%.0f%% opacity=%.2f extra_h=%.0f%% extra_opacity=%.2f",
            cfg.get("mask_y_percent", config.SUBTITLE_MASK_Y_PERCENT) * 100,
            cfg.get("mask_height_percent", config.SUBTITLE_MASK_HEIGHT_PERCENT) * 100,
            cfg.get("mask_opacity", config.SUBTITLE_MASK_OPACITY),
            cfg.get("mask_extra_height_percent", config.SUBTITLE_MASK_EXTRA_HEIGHT_PERCENT) * 100,
            cfg.get("mask_extra_opacity", config.SUBTITLE_MASK_EXTRA_OPACITY),
        )

    cmd = [
        "ffmpeg",
        "-i", input_video,
        "-vf", vf_string,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-c:a", "copy",
        "-y",
        output_path,
    ]

    logger.info(f"Rendering subtitled video → {output_path}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # Retry with aac audio encoding if stream copy fails
        logger.warning("FFmpeg audio copy failed, retrying with aac re-encoding...")
        cmd[cmd.index("copy")] = "aac"
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg subtitle render failed (exit {result.returncode}):\n{result.stderr}"
            )

    logger.info(f"Subtitled video rendered: {output_path}")
    return output_path
