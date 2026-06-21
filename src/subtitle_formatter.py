"""Subtitle Formatter — Utility to format, wrap, and clean subtitle texts for rendering."""
import re


def format_subtitle_text(text: str, max_chars_per_line: int = 42) -> str:
    """Format and wrap subtitle text to at most 2 lines of max_chars_per_line."""
    if not text:
        return ""
    
    # Normalize whitespaces
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars_per_line:
        return text

    words = text.split(" ")
    lines = []
    current_line = []

    for word in words:
        # Check if adding the word exceeds the line length limit
        if len(" ".join(current_line + [word])) <= max_chars_per_line:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    # Keep at most 2 lines, join back
    return "\n".join(lines[:2])
