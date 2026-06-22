"""Context-aware translator with adaptive windows, split-on-timeout, and resume support."""

import hashlib
import json
import os
import re
import time
from typing import Any

import requests

import config
from src.utils import setup_logging

logger = setup_logging("contextual_translator")

WINDOW_FILE_RE = re.compile(r"^window_(\d{4})_(\d{4})\.json$")


class TranslationPendingError(RuntimeError):
    def __init__(
        self,
        failed_windows: list[dict[str, Any]],
        completed_windows: list[str] | None = None,
        status_path: str | None = None,
    ) -> None:
        self.failed_windows = failed_windows
        self.completed_windows = completed_windows or []
        self.status_path = status_path

        failed_ranges = ", ".join(item.get("range", "unknown") for item in failed_windows) or "unknown"
        super().__init__(f"Translation incomplete. Failed windows: {failed_ranges}")


def build_window_prompt(
    video_context: dict,
    glossary: dict,
    character_bible: dict,
    prev_segs: list[dict],
    target_segs: list[dict],
    next_segs: list[dict],
    source_lang: str,
) -> str:
    def clean_segs(segs: list[dict]) -> list[dict]:
        return [{"id": s["id"], "text": s["text"], "duration": s["duration"]} for s in segs]

    prev_json = json.dumps(clean_segs(prev_segs), ensure_ascii=False, indent=2)
    target_json = json.dumps(clean_segs(target_segs), ensure_ascii=False, indent=2)
    next_json = json.dumps(clean_segs(next_segs), ensure_ascii=False, indent=2)

    prompt = f"""Bạn là biên dịch viên chuyên nghiệp lồng tiếng video từ {source_lang} sang tiếng Việt.

Nhiệm vụ:
- Dịch các segment trong TARGET_SEGMENTS sang tiếng Việt tự nhiên, phù hợp để lồng tiếng (TTS/dubbing).
- Sử dụng PREVIOUS_SEGMENTS và NEXT_SEGMENTS để hiểu mạch ngữ cảnh hội thoại, KHÔNG ĐƯỢC dịch các segment này.
- KHÔNG dịch từng chữ máy móc. Ưu tiên câu thoại ngắn gọn, văn phong nói tự nhiên.
- Dùng đúng xưng hô nhân vật theo CHARACTER_BIBLE.
- Tuân thủ để lại deixis policy và dịch thuật ngữ trong GLOSSARY.
- TUYỆT ĐỐI KHÔNG để sót bất kỳ ký tự tiếng Trung/Nhật/Hàn (CJK) nào trong literal_vi, dub_vi hoặc text_vi.
- Phù hợp với duration từng segment. Nếu câu dịch quá dài, hãy rút ngắn tự nhiên.

STRICT OUTPUT FORMAT:
Bạn bắt buộc phải phản hồi bằng 1 JSON object duy nhất có key "segments" chứa mảng kết quả của TARGET_SEGMENTS.
Không viết thêm lời giải thích hay bọc trong markdown code fence.

Expected JSON output format:
{{
  "segments": [
    {{
      "id": 1,
      "source_text": "text gốc",
      "literal_vi": "bản dịch nghĩa chính xác",
      "dub_vi": "bản lời thoại lồng tiếng Việt tối ưu cho phát âm TTS",
      "speaker": "SPEAKER_00 hoặc tên nhân vật tương ứng",
      "speaker_gender": "male / female / neutral",
      "pronoun_note": "ghi chú xưng hô nhân vật",
      "context_note": "ghi chú bối cảnh nếu có",
      "risk_flags": []
    }}
  ]
}}

VIDEO_CONTEXT:
{json.dumps(video_context, ensure_ascii=False, indent=2)}

GLOSSARY:
{json.dumps(glossary, ensure_ascii=False, indent=2)}

CHARACTER_BIBLE:
{json.dumps(character_bible, ensure_ascii=False, indent=2)}

PREVIOUS_SEGMENTS (chỉ dùng làm ngữ cảnh trước, KHÔNG dịch):
{prev_json}

TARGET_SEGMENTS (BẮT BUỘC dịch đầy đủ):
{target_json}

NEXT_SEGMENTS (chỉ dùng làm ngữ cảnh sau, KHÔNG dịch):
{next_json}
"""
    return prompt


def select_translation_window_size(total_segments: int) -> tuple[int, bool]:
    adaptive_enabled = config.TRANSLATION_ADAPTIVE_WINDOW_ENABLED
    if not adaptive_enabled:
        return config.TRANSLATION_WINDOW_SIZE, False

    if total_segments >= config.TRANSLATION_VERY_LONG_VIDEO_SEGMENT_THRESHOLD:
        return config.TRANSLATION_VERY_LONG_VIDEO_WINDOW_SIZE, True
    if total_segments >= config.TRANSLATION_LONG_VIDEO_SEGMENT_THRESHOLD:
        return config.TRANSLATION_LONG_VIDEO_WINDOW_SIZE, True
    return config.TRANSLATION_WINDOW_SIZE, True


def get_translation_window_status(work_dir: str) -> dict[str, Any] | None:
    status_path = os.path.join(work_dir, "translation_windows", "status.json")
    if not os.path.exists(status_path):
        return None
    try:
        with open(status_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logger.warning("[Translation] Failed to load status file %s: %s", status_path, exc)
        return None


def _stable_hash(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _window_key(start_id: int, end_id: int) -> str:
    return f"{start_id:04d}_{end_id:04d}"


def _write_json_atomic(path: str, payload: Any) -> None:
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def _extract_window_results(payload: Any) -> list[dict] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        segments = payload.get("segments")
        if isinstance(segments, list):
            return segments
    return None


def _validate_window_results(
    window_results: list[dict] | None,
    target_segs: list[dict],
) -> list[dict]:
    if not window_results or len(window_results) != len(target_segs):
        raise ValueError("Translated window did not return the expected segment count.")

    expected_ids = [int(seg["id"]) for seg in target_segs]
    actual_ids = [int(item.get("id", -1)) for item in window_results]
    if actual_ids != expected_ids:
        raise ValueError(f"Translated window IDs do not match target IDs: expected={expected_ids}, actual={actual_ids}")

    return window_results


def _load_window_file(path: str) -> list[dict] | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        window_results = _extract_window_results(payload)
        if not window_results:
            return None
        for item in window_results:
            if "id" not in item:
                return None
        return window_results
    except Exception:
        return None


def _group_missing_ids(missing_ids: list[int], window_size: int) -> list[tuple[int, int]]:
    if not missing_ids:
        return []

    ranges: list[tuple[int, int]] = []
    bucket: list[int] = [missing_ids[0]]

    for current_id in missing_ids[1:]:
        previous_id = bucket[-1]
        if current_id != previous_id + 1 or len(bucket) >= window_size:
            ranges.append((bucket[0], bucket[-1]))
            bucket = [current_id]
            continue
        bucket.append(current_id)

    if bucket:
        ranges.append((bucket[0], bucket[-1]))

    return ranges


def _compute_window_cache_hash(
    target_segs: list[dict],
    source_lang: str,
    video_context: dict,
    glossary: dict,
    character_bible: dict,
    translation_style: str,
) -> str:
    provider = config.TRANSLATION_PROVIDER
    model_name = getattr(config, f"{provider.upper()}_MODEL", "unknown")
    source_texts_hash = _stable_hash([seg.get("text", "") for seg in target_segs])
    payload = {
        "source_language": source_lang,
        "target_language": "vi-VN",
        "provider": provider,
        "model": model_name,
        "window_start": int(target_segs[0]["id"]),
        "window_end": int(target_segs[-1]["id"]),
        "source_texts_hash": source_texts_hash,
        "video_context_hash": _stable_hash(video_context or {}),
        "glossary_hash": _stable_hash(glossary or {}),
        "character_bible_hash": _stable_hash(character_bible or {}),
        "translation_style": translation_style or "",
    }
    return _stable_hash(payload)


def _load_window_from_global_cache(cache_hash: str) -> list[dict] | None:
    if not config.TRANSLATION_CACHE_ENABLED:
        return None
    cache_path = os.path.join(".cache", "translations", "windows", f"{cache_hash}.json")
    if not os.path.exists(cache_path):
        return None
    window_results = _load_window_file(cache_path)
    if window_results:
        logger.info("[Translation] cache hit for window hash %s", cache_hash[:12])
    return window_results


def _save_window_to_global_cache(cache_hash: str, window_results: list[dict]) -> None:
    if not config.TRANSLATION_CACHE_ENABLED:
        return
    cache_dir = os.path.join(".cache", "translations", "windows")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{cache_hash}.json")
    try:
        _write_json_atomic(cache_path, window_results)
    except Exception as exc:
        logger.warning("[Translation] Failed to save window cache %s: %s", cache_path, exc)


def _should_split_for_timeout(exc: Exception, segment_count: int) -> bool:
    if not config.TRANSLATION_ON_TIMEOUT_SPLIT_WINDOW:
        return False

    min_window_size = max(config.TRANSLATION_MIN_WINDOW_SIZE, 1)
    if segment_count < min_window_size * 2:
        return False

    queue = [exc]
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))

        if isinstance(current, (requests.ReadTimeout, requests.ConnectTimeout, requests.Timeout)):
            return True

        message = str(current).lower()
        if "read timed out" in message or "timeout" in message or "timed out" in message:
            return True

        for child in (getattr(current, "__cause__", None), getattr(current, "__context__", None)):
            if child is not None:
                queue.append(child)

    return False


def _merge_segment_translation(orig: dict, res: dict) -> dict:
    dub_vi = str(res.get("dub_vi", orig["text"]) or orig["text"]).strip()
    cleaned_text = re.sub(r"[^\w\s\d,.\-!?]", "", dub_vi).strip()
    if not cleaned_text:
        dub_vi = "Hả."

    literal_vi = str(res.get("literal_vi", dub_vi) or dub_vi).strip() or dub_vi
    speaker = str(res.get("speaker", "NARRATOR") or "NARRATOR").strip() or "NARRATOR"
    speaker_gender = str(res.get("speaker_gender", "neutral") or "neutral").strip() or "neutral"
    risk_flags = res.get("risk_flags", [])
    if not isinstance(risk_flags, list):
        risk_flags = [str(risk_flags)]

    return {
        "id": orig["id"],
        "text": orig["text"],
        "start": orig["start"],
        "end": orig["end"],
        "duration": orig["duration"],
        "literal_vi": literal_vi,
        "dub_vi": dub_vi,
        "text_vi": dub_vi,
        "subtitle_vi": dub_vi,
        "final_dub_vi": dub_vi,
        "speaker": speaker,
        "speaker_gender": speaker_gender,
        "context_note": str(res.get("context_note", "") or ""),
        "pronoun_note": str(res.get("pronoun_note", "") or ""),
        "risk_flags": risk_flags,
    }


def translate_segments_contextual(
    segments: list[dict],
    video_context: dict,
    glossary: dict,
    character_bible: dict,
    source_lang: str,
    work_dir: str | None = None,
) -> list[dict]:
    if not segments:
        return []

    total_segments = len(segments)
    window_size, adaptive_window = select_translation_window_size(total_segments)
    context_before = config.TRANSLATION_CONTEXT_BEFORE
    context_after = config.TRANSLATION_CONTEXT_AFTER
    translation_style = video_context.get("translation_style", "spoken Vietnamese")

    logger.info(
        "[Translation] total_segments=%s, adaptive_window=%s, window_size=%s",
        total_segments,
        adaptive_window,
        window_size,
    )

    windows_dir = None
    status_path = None
    if work_dir and config.TRANSLATION_PARTIAL_SAVE_ENABLED:
        windows_dir = os.path.join(work_dir, "translation_windows")
        os.makedirs(windows_dir, exist_ok=True)
        status_path = os.path.join(windows_dir, "status.json")

    segments_by_id = {int(seg["id"]): seg for seg in segments}
    segment_index_by_id = {int(seg["id"]): index for index, seg in enumerate(segments)}
    raw_results_by_id: dict[int, dict] = {}
    completed_ranges: set[str] = set()
    window_meta: dict[str, dict[str, Any]] = {}
    failed_windows: list[dict[str, Any]] = []

    if windows_dir and os.path.isdir(windows_dir):
        for entry in sorted(os.listdir(windows_dir)):
            match = WINDOW_FILE_RE.match(entry)
            if not match:
                continue

            start_id = int(match.group(1))
            end_id = int(match.group(2))
            range_key = _window_key(start_id, end_id)
            window_results = _load_window_file(os.path.join(windows_dir, entry))
            if not window_results:
                logger.warning("[Translation] Ignoring invalid partial window %s", entry)
                continue

            completed_ranges.add(range_key)
            window_meta[range_key] = {
                "status": "completed",
                "source": "partial_save",
                "segment_count": len(window_results),
            }
            for item in window_results:
                seg_id = int(item["id"])
                if seg_id in segments_by_id:
                    raw_results_by_id[seg_id] = item

    missing_ids = [int(seg["id"]) for seg in segments if int(seg["id"]) not in raw_results_by_id]
    pending_ranges: list[tuple[int, int]] = _group_missing_ids(missing_ids, window_size)

    logger.info(
        "[Translation] resume detected %s completed windows, %s pending windows",
        len(completed_ranges),
        len(pending_ranges),
    )

    def _save_status() -> None:
        if not status_path:
            return

        payload = {
            "total_segments": total_segments,
            "completed_windows": sorted(completed_ranges),
            "failed_windows": [item["range"] for item in failed_windows],
            "pending_windows": [_window_key(start_id, end_id) for start_id, end_id in pending_ranges],
            "provider": config.TRANSLATION_PROVIDER,
            "model": getattr(config, f"{config.TRANSLATION_PROVIDER.upper()}_MODEL", "unknown"),
            "window_size": window_size,
            "adaptive_window": adaptive_window,
            "windows": window_meta,
        }
        try:
            _write_json_atomic(status_path, payload)
        except Exception as exc:
            logger.warning("[Translation] Failed to save status file %s: %s", status_path, exc)

    def _remove_pending(range_tuple: tuple[int, int]) -> None:
        try:
            pending_ranges.remove(range_tuple)
        except ValueError:
            pass

    def _get_target_segments(start_id: int, end_id: int) -> list[dict]:
        return [
            seg
            for seg in segments
            if start_id <= int(seg["id"]) <= end_id
        ]

    def _mark_window_completed(
        range_key: str,
        window_results: list[dict],
        source: str,
        cache_hash: str | None = None,
    ) -> None:
        completed_ranges.add(range_key)
        window_meta[range_key] = {
            "status": "completed",
            "source": source,
            "segment_count": len(window_results),
            "cache_hash": cache_hash,
        }

        for item in window_results:
            raw_results_by_id[int(item["id"])] = item

    def _save_window_file(range_key: str, window_results: list[dict]) -> None:
        if not windows_dir:
            return
        path = os.path.join(windows_dir, f"window_{range_key}.json")
        _write_json_atomic(path, window_results)
        logger.info("[Translation] saved partial window_%s.json", range_key)

    def _translate_range(range_tuple: tuple[int, int]) -> None:
        start_id, end_id = range_tuple
        range_key = _window_key(start_id, end_id)
        target_segs = _get_target_segments(start_id, end_id)
        if not target_segs:
            _remove_pending(range_tuple)
            return

        if all(int(seg["id"]) in raw_results_by_id for seg in target_segs):
            _remove_pending(range_tuple)
            window_meta.setdefault(
                range_key,
                {"status": "completed", "source": "partial_save", "segment_count": len(target_segs)},
            )
            _save_status()
            return

        start_index = segment_index_by_id[int(target_segs[0]["id"])]
        end_index = segment_index_by_id[int(target_segs[-1]["id"])]
        prev_start = max(0, start_index - context_before)
        next_end = min(total_segments, end_index + 1 + context_after)
        prev_segs = segments[prev_start:start_index]
        next_segs = segments[end_index + 1:next_end]

        cache_hash = _compute_window_cache_hash(
            target_segs,
            source_lang,
            video_context,
            glossary,
            character_bible,
            translation_style,
        )

        cached_window = _load_window_from_global_cache(cache_hash)
        if cached_window:
            window_results = _validate_window_results(cached_window, target_segs)
            _save_window_file(range_key, window_results)
            _mark_window_completed(range_key, window_results, source="window_cache", cache_hash=cache_hash)
            _remove_pending(range_tuple)
            _save_status()
            return

        prompt = build_window_prompt(
            video_context,
            glossary,
            character_bible,
            prev_segs,
            target_segs,
            next_segs,
            source_lang,
        )

        window_label = f"window {range_key}"
        logger.info("[Translation] %s provider=%s attempt=1", window_label, config.TRANSLATION_PROVIDER)

        from src.ai import ai_router

        try:
            response_payload = ai_router.translate(prompt, request_label=window_label)
            window_results = _validate_window_results(_extract_window_results(response_payload), target_segs)
        except Exception as exc:
            if _should_split_for_timeout(exc, len(target_segs)):
                midpoint = len(target_segs) // 2
                left_range = (int(target_segs[0]["id"]), int(target_segs[midpoint - 1]["id"]))
                right_range = (int(target_segs[midpoint]["id"]), int(target_segs[-1]["id"]))
                left_key = _window_key(*left_range)
                right_key = _window_key(*right_range)
                logger.warning(
                    "[Translation] %s timeout after max retries, splitting into %s and %s",
                    window_label,
                    left_key,
                    right_key,
                )
                window_meta[range_key] = {
                    "status": "split",
                    "children": [left_key, right_key],
                    "segment_count": len(target_segs),
                    "error": str(exc),
                }
                _remove_pending(range_tuple)
                pending_ranges.extend([left_range, right_range])
                _save_status()
                _translate_range(left_range)
                _translate_range(right_range)
                return

            failure = {
                "range": range_key,
                "start_id": start_id,
                "end_id": end_id,
                "segment_count": len(target_segs),
                "provider": config.TRANSLATION_PROVIDER,
                "model": getattr(config, f"{config.TRANSLATION_PROVIDER.upper()}_MODEL", "unknown"),
                "error": str(exc),
            }
            window_meta[range_key] = {
                "status": "failed",
                "segment_count": len(target_segs),
                "error": str(exc),
            }
            failed_windows.append(failure)
            _remove_pending(range_tuple)
            _save_status()
            return

        _save_window_file(range_key, window_results)
        _save_window_to_global_cache(cache_hash, window_results)
        _mark_window_completed(range_key, window_results, source="generated", cache_hash=cache_hash)
        _remove_pending(range_tuple)
        _save_status()
        time.sleep(1.0)

    _save_status()

    for range_tuple in list(pending_ranges):
        if range_tuple not in pending_ranges:
            continue
        _translate_range(range_tuple)

    missing_after_run = [int(seg["id"]) for seg in segments if int(seg["id"]) not in raw_results_by_id]
    if failed_windows or missing_after_run:
        if missing_after_run:
            failed_ranges = _group_missing_ids(missing_after_run, window_size)
            known_failed = {item["range"] for item in failed_windows}
            for start_id, end_id in failed_ranges:
                range_key = _window_key(start_id, end_id)
                if range_key in known_failed:
                    continue
                failed_windows.append(
                    {
                        "range": range_key,
                        "start_id": start_id,
                        "end_id": end_id,
                        "segment_count": end_id - start_id + 1,
                        "provider": config.TRANSLATION_PROVIDER,
                        "model": getattr(config, f"{config.TRANSLATION_PROVIDER.upper()}_MODEL", "unknown"),
                        "error": "Missing translated segments after resume.",
                    }
                )
                window_meta.setdefault(
                    range_key,
                    {
                        "status": "failed",
                        "segment_count": end_id - start_id + 1,
                        "error": "Missing translated segments after resume.",
                    },
                )
        _save_status()
        raise TranslationPendingError(
            failed_windows=failed_windows,
            completed_windows=sorted(completed_ranges),
            status_path=status_path,
        )

    translated_segments = [
        _merge_segment_translation(seg, raw_results_by_id[int(seg["id"])])
        for seg in segments
    ]
    _save_status()
    logger.info("[Translation] completed %s translated segments", len(translated_segments))
    return translated_segments
