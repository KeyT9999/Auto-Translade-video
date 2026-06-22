from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from src.publisher import publish_to_facebook_detailed, publish_to_youtube_detailed
from src.utils import setup_logging

logger = setup_logging("publish_existing")


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load JSON %s: %s", path, exc)
        return default


def _save_json(path: str, payload) -> None:
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def _resolve_existing_video_path(work_dir: str, report: dict) -> str:
    file_candidates = []
    report_files = report.get("files", {}) if isinstance(report, dict) else {}
    if isinstance(report_files, dict):
        for key in ("dubbed_video", "subtitled_video"):
            value = report_files.get(key)
            if value:
                file_candidates.append(str(value))

    file_candidates.extend(
        [
            os.path.join(work_dir, "subtitled_video.mp4"),
            os.path.join(work_dir, "dubbed_video.mp4"),
        ]
    )

    for candidate in file_candidates:
        abs_candidate = os.path.abspath(candidate)
        if os.path.exists(abs_candidate):
            return abs_candidate

    raise FileNotFoundError(f"No existing rendered video found in session: {work_dir}")


def _load_publish_metadata(work_dir: str, report: dict) -> tuple[str, str, list[str]]:
    metadata_path = None
    report_files = report.get("files", {}) if isinstance(report, dict) else {}
    if isinstance(report_files, dict):
        metadata_path = report_files.get("youtube_metadata")

    if metadata_path:
        metadata_path = os.path.abspath(metadata_path)
    else:
        metadata_path = os.path.join(work_dir, "youtube_metadata.json")

    metadata = _load_json(metadata_path, {})
    title = str(metadata.get("title") or report.get("session_id") or os.path.basename(work_dir)).strip()
    description = str(metadata.get("description") or f"Published from existing session {os.path.basename(work_dir)}").strip()
    tags = metadata.get("hashtags", [])
    if not isinstance(tags, list):
        tags = []
    return title, description, [str(tag) for tag in tags]


def _update_report_publish_result(work_dir: str, platform: str, result: dict, video_path: str | None = None) -> dict:
    report_path = os.path.join(work_dir, "report.json")
    report = _load_json(report_path, {})
    if not isinstance(report, dict):
        report = {}

    published_urls = report.setdefault("published_urls", {})
    publish_status = report.setdefault("publish_status", {})
    publish_error = report.setdefault("publish_error", {})
    publish_meta = report.setdefault("publish_meta", {})

    success = bool(result.get("success"))
    published_urls[platform] = result.get("url") if success else published_urls.get(platform)
    publish_status[platform] = "success" if success else "failed"

    if success:
        publish_error.pop(platform, None)
    else:
        publish_error[platform] = str(result.get("error") or "Unknown publishing error")

    platform_meta = {
        "last_attempt_at": datetime.now(timezone.utc).isoformat(),
        "phase": result.get("phase"),
    }
    if video_path:
        platform_meta["video_path"] = video_path
    publish_meta[platform] = platform_meta

    report["status"] = report.get("status", "success")
    _save_json(report_path, report)
    return report


def publish_existing_session(session_dir: str, platform: str) -> dict:
    work_dir = os.path.abspath(session_dir)
    if not os.path.isdir(work_dir):
        raise FileNotFoundError(f"Session directory not found: {work_dir}")

    report_path = os.path.join(work_dir, "report.json")
    report = _load_json(report_path, {})
    video_path = _resolve_existing_video_path(work_dir, report)
    title, description, tags = _load_publish_metadata(work_dir, report)

    logger.info("Publish-only mode: reusing existing video %s", video_path)
    logger.info("Publish-only mode: session=%s platform=%s", work_dir, platform)

    if platform == "facebook":
        result = publish_to_facebook_detailed(video_path, title, description)
    elif platform == "youtube":
        result = publish_to_youtube_detailed(video_path, title, description, tags)
    else:
        raise ValueError(f"Unsupported platform: {platform}")

    updated_report = _update_report_publish_result(work_dir, platform, result, video_path=video_path)
    result["report"] = updated_report
    result["report_path"] = report_path
    result["video_path"] = video_path
    result["session_dir"] = work_dir
    return result
