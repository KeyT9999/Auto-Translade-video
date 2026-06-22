from src.subtitle_formatter import format_subtitle_text, split_timed_subtitle_chunks
from src.utils import format_timestamp, setup_logging

logger = setup_logging("srt_generator")


def generate_srt(
    segments: list[dict],
    output_path: str,
    text_field: str = "text",
    max_chars_per_line: int = 42,
) -> str:
    lines = []
    entry_index = 1
    for seg in segments:
        timed_chunks = split_timed_subtitle_chunks(
            seg["start"],
            seg["end"],
            seg[text_field],
            max_chars_per_line=max_chars_per_line,
            max_lines_per_chunk=2,
        )
        for chunk_start, chunk_end, chunk_text in timed_chunks:
            start_ts = format_timestamp(chunk_start)
            end_ts = format_timestamp(chunk_end)
            text = format_subtitle_text(
                chunk_text,
                max_chars_per_line=max_chars_per_line,
                max_lines=2,
                line_break="\n",
            )
            lines.append(f"{entry_index}\n{start_ts} --> {end_ts}\n{text}\n")
            entry_index += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"SRT written: {output_path} ({entry_index - 1} entries)")
    return output_path
