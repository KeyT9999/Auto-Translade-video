from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import config
from pipeline_vi import PipelineResult, run_single_video_pipeline
from src.publish_existing import publish_existing_session
from src.utils import ensure_dir, setup_logging

logger = setup_logging("batch_runner")

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCESS = "success"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_SKIPPED_DUPLICATE = "skipped_duplicate"
JOB_STATUS_RENDERED = "rendered"
JOB_STATUS_PUBLISH_FAILED = "publish_failed"
JOB_STATUS_PUBLISHED = "published"
JOB_STATUS_CANCELLED = "cancelled"

PIPELINE_SUCCESS_STATUSES = {
    JOB_STATUS_SUCCESS,
    JOB_STATUS_RENDERED,
    JOB_STATUS_PUBLISH_FAILED,
    JOB_STATUS_PUBLISHED,
}


@dataclass
class BatchJob:
    job_index: int
    url: str
    status: str = JOB_STATUS_PENDING
    attempts: int = 0
    output_dir: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error_step: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    rendered_video: str | None = None
    published_urls: dict[str, str | None] = field(
        default_factory=lambda: {"facebook": None, "youtube": None}
    )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BatchJob":
        return cls(
            job_index=int(payload.get("job_index", 0)),
            url=str(payload.get("url") or ""),
            status=str(payload.get("status") or JOB_STATUS_PENDING),
            attempts=int(payload.get("attempts", 0) or 0),
            output_dir=payload.get("output_dir"),
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            error_step=payload.get("error_step"),
            error_type=payload.get("error_type"),
            error_message=payload.get("error_message"),
            rendered_video=payload.get("rendered_video"),
            published_urls=_normalize_published_urls(payload.get("published_urls")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BatchState:
    batch_id: str
    batch_dir: str
    input_file: str | None
    links_file: str
    mode: str
    source_lang: str
    output_root: str
    publish_platforms: list[str]
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    stop_on_error: bool = config.BATCH_STOP_ON_ERROR
    continue_on_error: bool = config.BATCH_CONTINUE_ON_ERROR
    delay_between_videos_seconds: int = config.BATCH_DELAY_BETWEEN_VIDEOS_SECONDS
    retry_max_attempts: int = config.BATCH_RETRY_MAX_ATTEMPTS
    skip_duplicate_links: bool = config.BATCH_SKIP_DUPLICATE_LINKS
    write_markdown_report: bool = config.BATCH_WRITE_MARKDOWN_REPORT
    write_json_report: bool = config.BATCH_WRITE_JSON_REPORT
    dry_run: bool = False
    extra_options: dict[str, Any] = field(default_factory=dict)
    jobs: list[BatchJob] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BatchState":
        jobs = [BatchJob.from_dict(item) for item in payload.get("jobs", [])]
        return cls(
            batch_id=str(payload.get("batch_id") or ""),
            batch_dir=os.path.abspath(str(payload.get("batch_dir") or "")),
            input_file=payload.get("input_file"),
            links_file=os.path.abspath(str(payload.get("links_file") or "")),
            mode=str(payload.get("mode") or "subtitle_only"),
            source_lang=str(payload.get("source_lang") or config.DEFAULT_SOURCE_LANG),
            output_root=os.path.abspath(str(payload.get("output_root") or "./output/VN")),
            publish_platforms=_normalize_platforms(payload.get("publish_platforms")),
            created_at=str(payload.get("created_at") or _now_iso()),
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            stop_on_error=bool(payload.get("stop_on_error", config.BATCH_STOP_ON_ERROR)),
            continue_on_error=bool(
                payload.get("continue_on_error", config.BATCH_CONTINUE_ON_ERROR)
            ),
            delay_between_videos_seconds=int(
                payload.get(
                    "delay_between_videos_seconds",
                    config.BATCH_DELAY_BETWEEN_VIDEOS_SECONDS,
                )
            ),
            retry_max_attempts=max(
                1,
                int(payload.get("retry_max_attempts", config.BATCH_RETRY_MAX_ATTEMPTS)),
            ),
            skip_duplicate_links=bool(
                payload.get("skip_duplicate_links", config.BATCH_SKIP_DUPLICATE_LINKS)
            ),
            write_markdown_report=bool(
                payload.get("write_markdown_report", config.BATCH_WRITE_MARKDOWN_REPORT)
            ),
            write_json_report=bool(
                payload.get("write_json_report", config.BATCH_WRITE_JSON_REPORT)
            ),
            dry_run=bool(payload.get("dry_run", False)),
            extra_options=dict(payload.get("extra_options") or {}),
            jobs=jobs,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BatchReport:
    batch_id: str
    started_at: str | None
    finished_at: str | None
    total_jobs: int
    success: int
    published: int
    publish_failed: int
    failed: int
    skipped_duplicate: int
    rendered_only: int
    jobs: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _normalize_platforms(platforms: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for platform in platforms or []:
        value = str(platform).strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_published_urls(payload: Any) -> dict[str, str | None]:
    base = {"facebook": None, "youtube": None}
    if not isinstance(payload, dict):
        return base
    for key in base:
        value = payload.get(key)
        base[key] = str(value) if value else None
    return base


def normalize_url(url: str) -> str:
    stripped = url.strip()
    split = urlsplit(stripped)
    if not split.scheme or not split.netloc:
        return stripped

    path = split.path.rstrip("/") or split.path
    return urlunsplit(
        (split.scheme.lower(), split.netloc.lower(), path, split.query, "")
    )


def parse_links_file(input_path: str, max_links: int | None = None) -> list[str]:
    max_links = max_links or config.BATCH_MAX_LINKS
    with open(input_path, "r", encoding="utf-8") as handle:
        raw_lines = handle.readlines()

    return _parse_links_lines(raw_lines, max_links=max_links)


def parse_links_text(links_text: str, max_links: int | None = None) -> list[str]:
    max_links = max_links or config.BATCH_MAX_LINKS
    return _parse_links_lines(links_text.splitlines(), max_links=max_links)


def _parse_links_lines(raw_lines: list[str], *, max_links: int) -> list[str]:
    from src.utils import extract_url
    links = []
    for raw_line in raw_lines:
        line = raw_line.lstrip("\ufeff").strip()
        if not line or line.startswith("#"):
            continue
        cleaned = extract_url(line)
        if cleaned and (cleaned.startswith("http://") or cleaned.startswith("https://")):
            links.append(cleaned)

    if not links:
        raise ValueError("Input links file contains 0 links. Provide 1-50 links.")
    if len(links) > max_links:
        raise ValueError(
            f"Input links file contains {len(links)} links, which exceeds the maximum {max_links}."
        )
    return links


def create_batch_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return f"batch_{stamp}"


def _batch_json_path(batch_dir: str) -> str:
    return os.path.join(batch_dir, "batch.json")


def _batch_report_json_path(batch_dir: str) -> str:
    return os.path.join(batch_dir, "batch_report.json")


def _batch_report_md_path(batch_dir: str) -> str:
    return os.path.join(batch_dir, "batch_report.md")


def _job_dir(batch_dir: str, job_index: int) -> str:
    return os.path.join(batch_dir, "jobs", f"{job_index:03d}")


def _write_json(path: str, payload: Any) -> None:
    ensure_dir(os.path.dirname(path))
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def _write_text(path: str, text: str) -> None:
    ensure_dir(os.path.dirname(path))
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temp_path, path)


def _load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def attach_batch_log_file(batch_dir: str) -> str:
    log_path = os.path.abspath(os.path.join(batch_dir, "logs", "batch.log"))
    ensure_dir(os.path.dirname(log_path))

    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == log_path:
            return log_path

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(file_handler)
    return log_path


def save_batch_state(batch: BatchState) -> None:
    ensure_dir(batch.batch_dir)
    ensure_dir(os.path.join(batch.batch_dir, "jobs"))
    ensure_dir(os.path.join(batch.batch_dir, "logs"))
    _write_json(_batch_json_path(batch.batch_dir), batch.to_dict())

    for job in batch.jobs:
        job_dir = _job_dir(batch.batch_dir, job.job_index)
        ensure_dir(job_dir)
        _write_json(os.path.join(job_dir, "job.json"), job.to_dict())
        _write_text(os.path.join(job_dir, "session_link.txt"), f"{job.url}\n")
        _write_text(os.path.join(job_dir, "output_dir.txt"), f"{job.output_dir or ''}\n")


def load_batch_state(batch_dir: str) -> BatchState:
    payload = _load_json(_batch_json_path(batch_dir), None)
    if not isinstance(payload, dict):
        raise FileNotFoundError(f"Batch state not found: {_batch_json_path(batch_dir)}")
    return BatchState.from_dict(payload)


def build_batch_report(batch: BatchState) -> BatchReport:
    success = sum(1 for job in batch.jobs if job.status in PIPELINE_SUCCESS_STATUSES)
    published = sum(1 for job in batch.jobs if job.status == JOB_STATUS_PUBLISHED)
    publish_failed = sum(1 for job in batch.jobs if job.status == JOB_STATUS_PUBLISH_FAILED)
    failed = sum(1 for job in batch.jobs if job.status == JOB_STATUS_FAILED)
    skipped_duplicate = sum(
        1 for job in batch.jobs if job.status == JOB_STATUS_SKIPPED_DUPLICATE
    )
    rendered_only = sum(
        1 for job in batch.jobs if job.status in {JOB_STATUS_SUCCESS, JOB_STATUS_RENDERED}
    )

    jobs = []
    for job in batch.jobs:
        jobs.append(
            {
                "job_index": job.job_index,
                "url": job.url,
                "status": job.status,
                "attempts": job.attempts,
                "output_dir": job.output_dir,
                "rendered_video": job.rendered_video,
                "facebook_url": job.published_urls.get("facebook"),
                "youtube_url": job.published_urls.get("youtube"),
                "error_step": job.error_step,
                "error_type": job.error_type,
                "error_message": job.error_message,
            }
        )

    return BatchReport(
        batch_id=batch.batch_id,
        started_at=batch.started_at,
        finished_at=batch.finished_at,
        total_jobs=len(batch.jobs),
        success=success,
        published=published,
        publish_failed=publish_failed,
        failed=failed,
        skipped_duplicate=skipped_duplicate,
        rendered_only=rendered_only,
        jobs=jobs,
    )


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def write_batch_reports(batch: BatchState) -> BatchReport:
    report = build_batch_report(batch)

    if batch.write_json_report:
        _write_json(_batch_report_json_path(batch.batch_dir), report.to_dict())

    if batch.write_markdown_report:
        lines = [
            f"# Batch Report: {report.batch_id}",
            "",
            "## Summary",
            "",
            f"- Total: {report.total_jobs}",
            f"- Success: {report.success}",
            f"- Published: {report.published}",
            f"- Rendered only: {report.rendered_only}",
            f"- Publish failed: {report.publish_failed}",
            f"- Failed: {report.failed}",
            f"- Skipped duplicate: {report.skipped_duplicate}",
            "",
            "## Jobs",
            "",
            "| # | Status | URL | Output | Error |",
            "|---|--------|-----|--------|-------|",
        ]
        for job in batch.jobs:
            lines.append(
                "| {job_index} | {status} | {url} | {output_dir} | {error} |".format(
                    job_index=job.job_index,
                    status=_markdown_cell(job.status),
                    url=_markdown_cell(job.url),
                    output_dir=_markdown_cell(job.output_dir),
                    error=_markdown_cell(job.error_message),
                )
            )
        _write_text(_batch_report_md_path(batch.batch_dir), "\n".join(lines) + "\n")

    return report


def create_batch_state(
    input_path: str,
    *,
    mode: str,
    source_lang: str,
    output_root: str,
    publish_platforms: list[str] | None = None,
    extra_options: dict[str, Any] | None = None,
    batch_output_dir: str | None = None,
    dry_run: bool = False,
    stop_on_error: bool | None = None,
    continue_on_error: bool | None = None,
    delay_between_videos_seconds: int | None = None,
    retry_max_attempts: int | None = None,
    skip_duplicate_links: bool | None = None,
    write_markdown_report: bool | None = None,
    write_json_report: bool | None = None,
    batch_id: str | None = None,
) -> BatchState:
    input_path = os.path.abspath(input_path)
    links = parse_links_file(input_path)
    return create_batch_state_from_links(
        links,
        mode=mode,
        source_lang=source_lang,
        output_root=output_root,
        publish_platforms=publish_platforms,
        extra_options=extra_options,
        batch_output_dir=batch_output_dir,
        dry_run=dry_run,
        stop_on_error=stop_on_error,
        continue_on_error=continue_on_error,
        delay_between_videos_seconds=delay_between_videos_seconds,
        retry_max_attempts=retry_max_attempts,
        skip_duplicate_links=skip_duplicate_links,
        write_markdown_report=write_markdown_report,
        write_json_report=write_json_report,
        batch_id=batch_id,
        input_file=input_path,
    )


def create_batch_state_from_links(
    links: list[str],
    *,
    mode: str,
    source_lang: str,
    output_root: str,
    publish_platforms: list[str] | None = None,
    extra_options: dict[str, Any] | None = None,
    batch_output_dir: str | None = None,
    dry_run: bool = False,
    stop_on_error: bool | None = None,
    continue_on_error: bool | None = None,
    delay_between_videos_seconds: int | None = None,
    retry_max_attempts: int | None = None,
    skip_duplicate_links: bool | None = None,
    write_markdown_report: bool | None = None,
    write_json_report: bool | None = None,
    batch_id: str | None = None,
    input_file: str | None = None,
) -> BatchState:
    batch_output_dir = os.path.abspath(batch_output_dir or config.BATCH_OUTPUT_DIR)
    output_root = os.path.abspath(output_root)
    publish_platforms = _normalize_platforms(publish_platforms)
    extra_options = dict(extra_options or {})

    # Clean incoming links list to ensure URLs are extracted
    from src.utils import extract_url
    cleaned_links = []
    for url in links:
        cleaned = extract_url(url)
        if cleaned and (cleaned.startswith("http://") or cleaned.startswith("https://")):
            cleaned_links.append(cleaned)
        else:
            cleaned_links.append(cleaned or url)
    links = cleaned_links

    if not links:
        raise ValueError("Input links list contains 0 links. Provide 1-50 links.")
    if len(links) > config.BATCH_MAX_LINKS:
        raise ValueError(
            f"Input links list contains {len(links)} links, which exceeds the maximum {config.BATCH_MAX_LINKS}."
        )

    batch_id = batch_id or create_batch_id()
    batch_dir = os.path.join(batch_output_dir, batch_id)
    links_file = os.path.join(batch_dir, "links.txt")
    skip_duplicate_links = (
        config.BATCH_SKIP_DUPLICATE_LINKS if skip_duplicate_links is None else skip_duplicate_links
    )

    seen_urls: dict[str, int] = {}
    jobs: list[BatchJob] = []
    for index, url in enumerate(links, start=1):
        normalized = normalize_url(url)
        if skip_duplicate_links and normalized in seen_urls:
            jobs.append(
                BatchJob(
                    job_index=index,
                    url=url,
                    status=JOB_STATUS_SKIPPED_DUPLICATE,
                    error_type="DUPLICATE_URL",
                    error_message=f"Duplicate of job {seen_urls[normalized]:03d}.",
                )
            )
            continue

        seen_urls[normalized] = index
        jobs.append(BatchJob(job_index=index, url=url))

    resolved_stop_on_error = config.BATCH_STOP_ON_ERROR if stop_on_error is None else stop_on_error
    resolved_continue_on_error = (
        config.BATCH_CONTINUE_ON_ERROR if continue_on_error is None else continue_on_error
    )
    if resolved_stop_on_error:
        resolved_continue_on_error = False

    batch = BatchState(
        batch_id=batch_id,
        batch_dir=batch_dir,
        input_file=os.path.abspath(input_file) if input_file else None,
        links_file=links_file,
        mode=mode,
        source_lang=source_lang,
        output_root=output_root,
        publish_platforms=publish_platforms,
        created_at=_now_iso(),
        stop_on_error=resolved_stop_on_error,
        continue_on_error=resolved_continue_on_error,
        delay_between_videos_seconds=max(
            0,
            delay_between_videos_seconds
            if delay_between_videos_seconds is not None
            else config.BATCH_DELAY_BETWEEN_VIDEOS_SECONDS,
        ),
        retry_max_attempts=max(
            1,
            retry_max_attempts
            if retry_max_attempts is not None
            else config.BATCH_RETRY_MAX_ATTEMPTS,
        ),
        skip_duplicate_links=skip_duplicate_links,
        write_markdown_report=(
            config.BATCH_WRITE_MARKDOWN_REPORT
            if write_markdown_report is None
            else write_markdown_report
        ),
        write_json_report=(
            config.BATCH_WRITE_JSON_REPORT if write_json_report is None else write_json_report
        ),
        dry_run=dry_run,
        extra_options=extra_options,
        jobs=jobs,
    )

    ensure_dir(batch.batch_dir)
    _write_text(links_file, "\n".join(links) + "\n")
    attach_batch_log_file(batch.batch_dir)
    save_batch_state(batch)
    write_batch_reports(batch)
    return batch


def _find_existing_rendered_video(output_dir: str | None) -> str | None:
    if not output_dir:
        return None
    for filename in ("subtitled_video.mp4", "dubbed_video.mp4"):
        candidate = os.path.join(output_dir, filename)
        if os.path.exists(candidate):
            return candidate
    return None


def _classify_publish_error(message: str | None) -> str:
    lowered = str(message or "").lower()
    if "facebook" in lowered and any(token in lowered for token in ("oauth", "token", "190", "463")):
        return "FACEBOOK_TOKEN_EXPIRED"
    if "youtube" in lowered and any(token in lowered for token in ("oauth", "auth", "credential")):
        return "YOUTUBE_AUTH_FAILED"
    return "PUBLISH_FAILED"


class BatchRunner:
    def __init__(
        self,
        *,
        pipeline_runner: Callable[..., PipelineResult] = run_single_video_pipeline,
        publish_runner: Callable[[str, str], dict[str, Any]] = publish_existing_session,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.pipeline_runner = pipeline_runner
        self.publish_runner = publish_runner
        self.sleeper = sleeper

    def run(
        self,
        batch: BatchState,
        *,
        retry_failed: bool = False,
        retry_publish_platforms: list[str] | None = None,
    ) -> BatchState:
        attach_batch_log_file(batch.batch_dir)
        retry_publish_platforms = _normalize_platforms(retry_publish_platforms)
        self._recover_interrupted_jobs(batch)

        if batch.started_at is None:
            batch.started_at = _now_iso()
        batch.finished_at = None
        save_batch_state(batch)
        write_batch_reports(batch)

        if batch.dry_run:
            logger.info("Dry run for batch %s completed after queue creation.", batch.batch_id)
            batch.finished_at = _now_iso()
            save_batch_state(batch)
            write_batch_reports(batch)
            return batch

        for index, job in enumerate(batch.jobs):
            action = self._determine_action(
                batch,
                job,
                retry_failed=retry_failed,
                retry_publish_platforms=retry_publish_platforms,
            )
            if action is None:
                continue

            if action == "process":
                self._run_pipeline_job(batch, job)
            elif action == "retry_publish":
                self._retry_publish_job(
                    batch,
                    job,
                    retry_publish_platforms or batch.publish_platforms,
                )

            save_batch_state(batch)
            write_batch_reports(batch)

            if self._should_stop_after_error(batch, job):
                logger.warning("Stopping batch %s after job %03d error.", batch.batch_id, job.job_index)
                break

            if self._has_follow_up_work(
                batch,
                start_index=index + 1,
                retry_failed=retry_failed,
                retry_publish_platforms=retry_publish_platforms,
            ) and batch.delay_between_videos_seconds > 0:
                self.sleeper(batch.delay_between_videos_seconds)

        batch.finished_at = _now_iso()
        save_batch_state(batch)
        write_batch_reports(batch)
        return batch

    def _recover_interrupted_jobs(self, batch: BatchState) -> None:
        changed = False
        for job in batch.jobs:
            if job.status == JOB_STATUS_RUNNING:
                job.status = JOB_STATUS_PENDING
                job.finished_at = None
                changed = True
        if changed:
            save_batch_state(batch)

    def _determine_action(
        self,
        batch: BatchState,
        job: BatchJob,
        *,
        retry_failed: bool,
        retry_publish_platforms: list[str],
    ) -> str | None:
        if job.status in {JOB_STATUS_SKIPPED_DUPLICATE, JOB_STATUS_CANCELLED, JOB_STATUS_PUBLISHED}:
            return None

        if retry_publish_platforms:
            if job.status in {JOB_STATUS_SUCCESS, JOB_STATUS_RENDERED, JOB_STATUS_PUBLISH_FAILED}:
                return "retry_publish" if job.output_dir else None
            return None

        if job.status == JOB_STATUS_PENDING:
            return "process"

        if retry_failed and config.BATCH_RETRY_FAILED_ENABLED and job.status == JOB_STATUS_FAILED:
            if job.attempts >= batch.retry_max_attempts:
                logger.warning(
                    "Skipping job %03d: attempts=%s reached retry_max_attempts=%s",
                    job.job_index,
                    job.attempts,
                    batch.retry_max_attempts,
                )
                return None
            return "process"

        return None

    def _has_follow_up_work(
        self,
        batch: BatchState,
        *,
        start_index: int,
        retry_failed: bool,
        retry_publish_platforms: list[str],
    ) -> bool:
        for job in batch.jobs[start_index:]:
            if self._determine_action(
                batch,
                job,
                retry_failed=retry_failed,
                retry_publish_platforms=retry_publish_platforms,
            ):
                return True
        return False

    def _run_pipeline_job(self, batch: BatchState, job: BatchJob) -> None:
        logger.info("Running batch %s job %03d", batch.batch_id, job.job_index)
        job.status = JOB_STATUS_RUNNING
        job.attempts += 1
        job.started_at = _now_iso()
        job.finished_at = None
        job.error_step = None
        job.error_type = None
        job.error_message = None
        save_batch_state(batch)
        write_batch_reports(batch)

        extra_options = dict(batch.extra_options)
        extra_options["source_lang"] = batch.source_lang
        result = self.pipeline_runner(
            source_url=job.url,
            mode=batch.mode,
            target_language="vi-VN",
            publish_platforms=batch.publish_platforms,
            output_root=batch.output_root,
            batch_id=batch.batch_id,
            job_index=job.job_index,
            extra_options=extra_options,
        )

        job.output_dir = os.path.abspath(result.output_dir) if result.output_dir else None
        job.rendered_video = result.rendered_video or _find_existing_rendered_video(job.output_dir)
        job.finished_at = _now_iso()
        job.error_step = result.error_step
        job.error_type = result.error_type
        job.error_message = result.error_message
        job.published_urls = _normalize_published_urls(result.published_urls)
        job.status = self._status_from_pipeline_result(batch, job, result)

    def _status_from_pipeline_result(
        self,
        batch: BatchState,
        job: BatchJob,
        result: PipelineResult,
    ) -> str:
        expected_publish_platforms = batch.publish_platforms

        if not result.success:
            if job.rendered_video:
                return JOB_STATUS_PUBLISH_FAILED if expected_publish_platforms else JOB_STATUS_RENDERED
            return JOB_STATUS_FAILED

        if expected_publish_platforms:
            if all(job.published_urls.get(platform) for platform in expected_publish_platforms):
                return JOB_STATUS_PUBLISHED
            return JOB_STATUS_PUBLISH_FAILED

        if job.rendered_video:
            return JOB_STATUS_SUCCESS
        return JOB_STATUS_SUCCESS

    def _retry_publish_job(
        self,
        batch: BatchState,
        job: BatchJob,
        platforms: list[str],
    ) -> None:
        logger.info("Retrying publish for batch %s job %03d", batch.batch_id, job.job_index)
        job.status = JOB_STATUS_RUNNING
        job.attempts += 1
        job.started_at = _now_iso()
        job.finished_at = None
        save_batch_state(batch)
        write_batch_reports(batch)

        job.output_dir = os.path.abspath(job.output_dir) if job.output_dir else None
        if not job.output_dir:
            job.status = JOB_STATUS_PUBLISH_FAILED
            job.finished_at = _now_iso()
            job.error_step = "publish"
            job.error_type = "PUBLISH_FAILED"
            job.error_message = "Missing output_dir for publish-only retry."
            return

        errors: list[str] = []
        last_error_type: str | None = None
        for platform in platforms:
            result = self.publish_runner(job.output_dir, platform)
            if result.get("success"):
                job.published_urls[platform] = result.get("url")
                if result.get("video_path"):
                    job.rendered_video = result["video_path"]
                continue

            error_message = str(result.get("error") or f"Publish to {platform} failed.")
            errors.append(f"{platform}: {error_message}")
            last_error_type = _classify_publish_error(error_message)

        job.rendered_video = job.rendered_video or _find_existing_rendered_video(job.output_dir)
        job.finished_at = _now_iso()

        expected_publish_platforms = batch.publish_platforms or platforms
        if expected_publish_platforms and all(
            job.published_urls.get(platform) for platform in expected_publish_platforms
        ):
            job.status = JOB_STATUS_PUBLISHED
            job.error_step = None
            job.error_type = None
            job.error_message = None
            return

        job.status = JOB_STATUS_PUBLISH_FAILED
        job.error_step = "publish"
        job.error_type = last_error_type or "PUBLISH_FAILED"
        job.error_message = "; ".join(errors) if errors else "Publish retry did not complete."

    def _should_stop_after_error(self, batch: BatchState, job: BatchJob) -> bool:
        if job.status not in {JOB_STATUS_FAILED, JOB_STATUS_PUBLISH_FAILED}:
            return False
        return batch.stop_on_error or not batch.continue_on_error
