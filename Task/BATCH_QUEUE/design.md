# Design: Batch Queue for Sequential Video Processing

## 1. Design Principles

- Reuse the current single-video Vietnamese pipeline instead of copying it.
- Persist all batch/job state to files so resume is simple and durable.
- Process one job at a time only.
- Keep the old `pipeline_vi.py` CLI behavior unchanged.
- Make job transitions explicit and easy to inspect from JSON files.

## 2. High-Level Architecture

```text
tools/batch_runner.py
-> parse CLI
-> load config
-> parse links / resume batch
-> build BatchState + BatchJob files
-> choose next runnable job
-> call single-video wrapper
-> update job.json + batch.json
-> update reports
-> continue sequentially
```

## 3. Proposed Modules

### `tools/batch_runner.py`

Responsibilities:

- User-facing CLI for batch execution.
- New batch creation.
- Resume existing batch.
- Retry failed jobs.
- Retry publish-only jobs.

### `src/batch_runner.py`

Responsibilities:

- Batch/job dataclasses.
- Batch state loading/saving.
- Link parsing and validation.
- Queue creation.
- Sequential execution loop.
- Report generation.

### `pipeline_vi.py`

Responsibilities after refactor:

- Continue exposing current CLI.
- Expose a reusable single-video wrapper that returns structured results.

## 4. Data Model

### `PipelineResult`

```python
@dataclass
class PipelineResult:
    success: bool
    output_dir: str | None
    rendered_video: str | None
    report_path: str | None
    published_urls: dict[str, str | None]
    error_step: str | None
    error_type: str | None
    error_message: str | None
```

### `BatchJob`

```python
@dataclass
class BatchJob:
    job_index: int
    url: str
    status: str = "pending"
    attempts: int = 0
    output_dir: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error_step: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    rendered_video: str | None = None
    published_urls: dict[str, str | None] = field(default_factory=lambda: {"facebook": None, "youtube": None})
```

### `BatchState`

```python
@dataclass
class BatchState:
    batch_id: str
    batch_dir: str
    input_file: str | None
    links_file: str
    mode: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    stop_on_error: bool
    continue_on_error: bool
    delay_between_videos_seconds: int
    publish_platforms: list[str]
    dry_run: bool
    jobs: list[BatchJob]
```

## 5. File Layout

```text
output/batches/<batch_id>/
  batch.json
  batch_report.json
  batch_report.md
  links.txt
  logs/
    batch.log
  jobs/
    001/
      job.json
      session_link.txt
      output_dir.txt
```

Design decision:

- `batch.json` is the canonical batch state.
- Each `jobs/<nnn>/job.json` mirrors the per-job state for easy inspection and crash recovery.
- Reports are regenerated after each job so progress is never lost.

## 6. Sequential Execution Flow

For a new batch:

```text
read links
-> normalize and validate
-> create batch_id
-> create BatchJob records
-> save batch.json and job.json files
-> if dry-run: stop after report generation
-> else process job 1..N in order
```

For each job:

```text
pending
-> running
-> call run_single_video_pipeline(...)
-> success/rendered/published/publish_failed/failed
-> write job.json
-> write batch.json
-> regenerate reports
-> sleep configured delay before next job
```

## 7. Status Mapping Rules

From `PipelineResult` plus publish intent:

- `success=True`, no publish requested -> `success`
- `success=True`, publish requested but no platform succeeded yet and render exists -> `rendered`
- `success=True`, publish requested and all requested publishes succeeded -> `published`
- `success=True`, render exists but at least one requested publish failed -> `publish_failed`
- `success=False` -> `failed`

Duplicate handling:

- If a URL repeats later in the same batch and duplicate skip is enabled, mark later jobs as `skipped_duplicate`.

## 8. Resume Strategy

Resume uses the persisted batch files only.

Normal resume runs:

- skip `success`
- skip `rendered`
- skip `published`
- skip `skipped_duplicate`
- process `pending`
- process `running` as recoverable and reset to `pending`
- process `failed` only if retry mode says so
- process `publish_failed` only if publish retry mode says so

Recovery rule:

- If the process died while a job was `running`, convert it back to `pending` on resume because the prior attempt did not finish cleanly.

## 9. Retry Strategy

### `--retry-failed`

- rerun jobs with `failed`
- respect max attempts
- do not rerun successful jobs

### `--retry-publish <platform>`

- target jobs with `rendered` or `publish_failed`
- call publish-only helper with the existing `output_dir`
- do not rerun translation or rendering

## 10. Error Classification

Standard error types:

```text
DOWNLOAD_FAILED
ASR_FAILED
TRANSLATION_FAILED
VALIDATION_FAILED
RENDER_FAILED
METADATA_FAILED
PUBLISH_FAILED
FACEBOOK_TOKEN_EXPIRED
YOUTUBE_AUTH_FAILED
UNKNOWN_ERROR
```

Design rule:

- Error type is classified in the single-video wrapper when possible.
- If no specific classification is possible, fall back to `UNKNOWN_ERROR`.
- Publish errors must not collapse a fully rendered job into generic `failed`.

## 11. Publish-Only Retry Design

Existing reusable asset:

- `src.publish_existing.publish_existing_session(session_dir, platform)`

Batch retry-publish flow:

```text
job status rendered/publish_failed
-> resolve output_dir from job.json
-> call publish_existing_session(output_dir, platform)
-> update published_urls
-> set status to published if requested publish succeeds for all targeted platforms
-> otherwise keep publish_failed
```

## 12. Reporting Design

### JSON Report

Generated from `BatchState` after each job and at the end.

Includes:

- summary counters by status
- started/finished timestamps
- per-job outcome
- output directory
- rendered video path
- published URLs
- error details

### Markdown Report

Human-readable dashboard with:

- summary
- status table
- output path references
- short error text per job

## 13. Configuration Design

`config.py` gains batch constants.

Special handling:

- `BATCH_PROCESS_CONCURRENCY` is parsed from env.
- If value is below `1`, clamp to `1`.
- If value is above `1`, log a warning and clamp to `1`.

## 14. Testing Strategy

Unit tests mock the single-video wrapper.

Focus:

- link parsing limits
- duplicate skipping
- queue creation
- sequential execution order
- continue-on-error behavior
- stop-on-error behavior
- resume selection
- retry-failed selection
- retry-publish selection
- JSON and Markdown report generation

No real API calls should run in batch tests.
