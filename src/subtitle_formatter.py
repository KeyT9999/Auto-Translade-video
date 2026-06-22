"""Subtitle text formatting and display chunk helpers."""

from __future__ import annotations

import re

WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;…])\s+")
PAUSE_SPLIT_RE = re.compile(r"(?<=[,:])\s+")


def normalize_subtitle_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text or "").strip()


def wrap_subtitle_lines(text: str, max_chars_per_line: int = 42) -> list[str]:
    normalized = normalize_subtitle_text(text)
    if not normalized:
        return []
    if len(normalized) <= max_chars_per_line:
        return [normalized]

    words = normalized.split(" ")
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

    return lines


def format_subtitle_text(
    text: str,
    max_chars_per_line: int = 42,
    max_lines: int = 2,
    line_break: str = "\n",
) -> str:
    """Format and wrap subtitle text to at most max_lines lines."""
    lines = wrap_subtitle_lines(text, max_chars_per_line=max_chars_per_line)
    return line_break.join(lines[:max_lines])


def _chunk_fits(text: str, max_chars_per_line: int, max_lines_per_chunk: int) -> bool:
    return len(wrap_subtitle_lines(text, max_chars_per_line=max_chars_per_line)) <= max_lines_per_chunk


def _group_lines_into_chunks(
    lines: list[str],
    max_lines_per_chunk: int,
) -> list[str]:
    chunks: list[str] = []
    for index in range(0, len(lines), max_lines_per_chunk):
        chunk_lines = lines[index:index + max_lines_per_chunk]
        if chunk_lines:
            chunks.append(" ".join(chunk_lines))
    return chunks


def _split_oversized_unit(
    unit: str,
    max_chars_per_line: int,
    max_lines_per_chunk: int,
) -> list[str]:
    normalized = normalize_subtitle_text(unit)
    if not normalized:
        return []
    if _chunk_fits(normalized, max_chars_per_line, max_lines_per_chunk):
        return [normalized]

    fine_units = [part.strip() for part in PAUSE_SPLIT_RE.split(normalized) if part.strip()]
    if len(fine_units) > 1:
        return _pack_units_into_chunks(
            fine_units,
            max_chars_per_line=max_chars_per_line,
            max_lines_per_chunk=max_lines_per_chunk,
        )

    lines = wrap_subtitle_lines(normalized, max_chars_per_line=max_chars_per_line)
    return _group_lines_into_chunks(lines, max_lines_per_chunk=max_lines_per_chunk)


def _pack_units_into_chunks(
    units: list[str],
    max_chars_per_line: int,
    max_lines_per_chunk: int,
) -> list[str]:
    chunks: list[str] = []
    current_units: list[str] = []

    for unit in units:
        candidate = " ".join(current_units + [unit]).strip()
        if candidate and _chunk_fits(candidate, max_chars_per_line, max_lines_per_chunk):
            current_units.append(unit)
            continue

        if current_units:
            chunks.append(" ".join(current_units).strip())
            current_units = []

        oversized_parts = _split_oversized_unit(
            unit,
            max_chars_per_line=max_chars_per_line,
            max_lines_per_chunk=max_lines_per_chunk,
        )
        if not oversized_parts:
            continue
        chunks.extend(oversized_parts[:-1])
        current_units = [oversized_parts[-1]]

    if current_units:
        chunks.append(" ".join(current_units).strip())

    return [chunk for chunk in chunks if chunk]


def split_subtitle_text_into_chunks(
    text: str,
    max_chars_per_line: int = 42,
    max_lines_per_chunk: int = 2,
) -> list[str]:
    normalized = normalize_subtitle_text(text)
    if not normalized:
        return []
    if _chunk_fits(normalized, max_chars_per_line, max_lines_per_chunk):
        return [normalized]

    sentence_units = [part.strip() for part in SENTENCE_SPLIT_RE.split(normalized) if part.strip()]
    if len(sentence_units) <= 1:
        sentence_units = [normalized]

    chunks = _pack_units_into_chunks(
        sentence_units,
        max_chars_per_line=max_chars_per_line,
        max_lines_per_chunk=max_lines_per_chunk,
    )
    return chunks or [normalized]


def split_timed_subtitle_chunks(
    start: float,
    end: float,
    text: str,
    max_chars_per_line: int = 42,
    max_lines_per_chunk: int = 2,
    min_duration_for_multi_chunk: float = 4.0,
) -> list[tuple[float, float, str]]:
    chunks = split_subtitle_text_into_chunks(
        text,
        max_chars_per_line=max_chars_per_line,
        max_lines_per_chunk=max_lines_per_chunk,
    )
    if not chunks:
        return []

    duration = max(float(end) - float(start), 0.0)
    if len(chunks) == 1 or duration < min_duration_for_multi_chunk:
        return [(float(start), float(end), chunks[0])]

    total_weight = sum(max(len(chunk.replace(" ", "")), 1) for chunk in chunks)
    current_start = float(start)
    timed_chunks: list[tuple[float, float, str]] = []

    for index, chunk in enumerate(chunks):
        if index == len(chunks) - 1:
            chunk_end = float(end)
        else:
            weight = max(len(chunk.replace(" ", "")), 1) / total_weight
            chunk_end = current_start + duration * weight
        timed_chunks.append((current_start, chunk_end, chunk))
        current_start = chunk_end

    return timed_chunks
