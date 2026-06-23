# Requirement: Batch Queue Input 1-50 Link

## 1. Background

The current Vietnamese pipeline already handles one video well:

```text
input link
-> download video
-> extract audio
-> ASR
-> translate
-> validate/repair
-> subtitle-only render
-> metadata
-> publish if enabled
-> report
```

The new requirement is a file-based batch queue that accepts `1-50` links and processes them one by one without parallel execution.

## 2. Primary Goal

Add a batch runner that can:

```text
input 1-50 links
-> create batch_id
-> create batch folder
-> create queue entries
-> process job 1
-> render/publish/report
-> move to job 2
-> continue until the last job
```

The batch feature must be additive only. The existing single-video workflow must keep working as-is.

## 3. Scope

In scope:

- Read links from `.txt` input.
- Validate link count from `1` to `50`.
- Create `batch_id` and `output/batches/<batch_id>/`.
- Create persistent batch/job state files.
- Process jobs sequentially only.
- Continue after job failure by default.
- Support resume after interruption.
- Support retry for failed jobs.
- Support publish-only retry for rendered jobs.
- Generate JSON and Markdown batch reports.

Out of scope for this phase:

- Parallel processing.
- Database-backed queue.
- Distributed workers.
- Complex scheduler/orchestrator.

## 4. CLI Requirements

Supported entrypoint:

```bash
python tools/batch_runner.py --input links.txt --mode subtitle_only
```

Examples:

```bash
python tools/batch_runner.py --input links.txt --mode subtitle_only --publish facebook
python tools/batch_runner.py --input links.txt --mode subtitle_only --cover-original-subtitles --subtitle-style boxed
python tools/batch_runner.py --resume output/batches/batch_20260622_132500
python tools/batch_runner.py --resume output/batches/batch_20260622_132500 --retry-failed
python tools/batch_runner.py --resume output/batches/batch_20260622_132500 --retry-publish facebook
python tools/batch_runner.py --input links.txt --dry-run
```

## 5. Input / Output

### Input

- `links.txt` containing `1-50` URLs, one per line.
- Existing single-video pipeline options that are still relevant for subtitle-only rendering and publish.
- Resume mode that targets an existing batch folder.

### Output

Batch root:

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

Each job still writes its own existing session output under the normal video output root, for example:

```text
output/VN/20260622130622_vi/
  transcript_original.json
  transcript_vi.json
  transcript_vi.srt
  transcript_vi.ass
  subtitled_video.mp4
  report.json
```

## 6. Job Status Model

Supported statuses:

```text
pending
running
success
failed
skipped_duplicate
rendered
publish_failed
published
cancelled
```

Semantics:

- `pending`: job exists but has not started.
- `running`: job is being processed right now.
- `success`: processing finished successfully and no publish was requested.
- `rendered`: render finished and output video exists, but publish was not completed yet.
- `published`: render finished and requested publish succeeded.
- `publish_failed`: render succeeded, but publish failed.
- `failed`: pipeline failed before render was considered complete.
- `skipped_duplicate`: skipped because the URL duplicates an earlier batch job when duplicate skipping is enabled.
- `cancelled`: stopped manually.

## 7. Resume and Retry Requirements

Resume:

- Read `batch.json`.
- Skip jobs already marked `success`, `rendered`, or `published`, unless a retry mode explicitly targets them.
- Continue with remaining jobs in order.
- Do not rerun successful jobs during normal resume.

Retry failed:

- `--retry-failed` may rerun jobs with `failed`.
- `publish_failed` may be retried only when publish retry is explicitly requested.

Retry publish-only:

- `--retry-publish facebook` or `--retry-publish youtube`.
- Reuse the existing rendered video from the session output.
- Must not re-download, re-translate, or re-render the source video.

## 8. Configuration Requirements

Add batch-related config to `.env.example` and `config.py`:

```env
BATCH_MAX_LINKS=50
BATCH_PROCESS_CONCURRENCY=1
BATCH_CONTINUE_ON_ERROR=true
BATCH_STOP_ON_ERROR=false
BATCH_RETRY_FAILED_ENABLED=true
BATCH_RETRY_MAX_ATTEMPTS=2
BATCH_DELAY_BETWEEN_VIDEOS_SECONDS=10
BATCH_SKIP_DUPLICATE_LINKS=true
BATCH_OUTPUT_DIR=./output/batches
BATCH_WRITE_MARKDOWN_REPORT=true
BATCH_WRITE_JSON_REPORT=true
BATCH_AUTO_PUBLISH_ENABLED=false
```

Important rule:

- `BATCH_PROCESS_CONCURRENCY` is forced to `1`.
- If the environment sets a value greater than `1`, the application must warn and clamp it back to `1`.

## 9. Integration Requirements

The batch runner must not duplicate the whole single-video pipeline.

Preferred integration:

- Add a clear callable wrapper for one video.
- Batch runner calls that function and receives a structured result.

Fallback is allowed only if needed:

- Spawn the single-video CLI as a subprocess.

Preferred callable shape:

```python
run_single_video_pipeline(
    source_url: str,
    mode: str,
    target_language: str = "vi-VN",
    publish_platforms: list[str] | None = None,
    output_root: str = "./output/VN",
    batch_id: str | None = None,
    job_index: int | None = None,
    extra_options: dict | None = None,
) -> PipelineResult
```

## 10. Reporting Requirements

The batch runner must generate:

- `batch_report.json`
- `batch_report.md`

Minimum summary fields:

- `batch_id`
- `started_at`
- `finished_at`
- `total_jobs`
- `success`
- `published`
- `publish_failed`
- `failed`
- `skipped_duplicate`
- per-job details

## 11. Non-Regression Requirements

- Existing single-video commands keep the same behavior.
- Subtitle-only mode must still skip TTS, speaker audio synthesis, and audio merge steps.
- Batch mode must be an extra feature, not a replacement for current CLI usage.

## 12. Acceptance Criteria

- `Task/BATCH_QUEUE/requirement.md` exists.
- `Task/BATCH_QUEUE/design.md` exists.
- `Task/BATCH_QUEUE/task.md` exists.
- `Task/BATCH_QUEUE/phase_plan.md` exists.
- `tools/batch_runner.py` exists.
- One-link batch works.
- Multi-link batch runs sequentially in order.
- More than `50` links is rejected clearly.
- Duplicate links are skipped when configured.
- One failed job does not stop the whole batch by default.
- Batch writes `batch.json`, `batch_report.json`, and `batch_report.md`.
- Resume does not rerun successful jobs.
- Retry-failed only reruns failed jobs.
- Retry-publish reuses the rendered video without translation/render rerun.
- Existing single-video workflow still works.
- Tests pass.
