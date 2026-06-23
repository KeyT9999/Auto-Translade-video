# Phase Plan: Batch Queue

## Phase 1: Documentation

Goal:
Lock the batch queue contract before implementation.

Deliverables:

- `Task/BATCH_QUEUE/requirement.md`
- `Task/BATCH_QUEUE/design.md`
- `Task/BATCH_QUEUE/task.md`
- `Task/BATCH_QUEUE/phase_plan.md`

## Phase 2: Config

Goal:
Introduce batch configuration without changing current single-video defaults.

Deliverables:

- Batch env keys in `.env.example`
- Batch config constants in `config.py`
- Concurrency clamp to `1`

## Phase 3: Reusable Single-Video Wrapper

Goal:
Expose one stable function for batch execution to call.

Deliverables:

- `PipelineResult`
- `run_single_video_pipeline(...)`
- error classification
- publish outcome mapping

## Phase 4: Batch State and Persistence

Goal:
Make the queue file-based, durable, and resume-friendly.

Deliverables:

- `BatchJob`
- `BatchState`
- helpers for atomic state writes
- `batch.json`
- `jobs/<nnn>/job.json`

## Phase 5: Batch Runner CLI

Goal:
Provide a practical entrypoint for new batch runs and resume flows.

Deliverables:

- `tools/batch_runner.py`
- new batch creation
- resume mode
- retry flags
- dry-run mode

## Phase 6: Sequential Execution

Goal:
Process each job one at a time with clear state transitions.

Deliverables:

- ordered execution loop
- per-job status updates
- continue-on-error behavior
- stop-on-error behavior
- delay between videos

## Phase 7: Resume and Retry

Goal:
Allow interrupted or partial batches to recover without wasted work.

Deliverables:

- resume pending jobs
- skip successful jobs
- retry failed jobs
- publish-only retry using existing rendered sessions

## Phase 8: Reports

Goal:
Produce machine-readable and human-readable batch summaries.

Deliverables:

- `batch_report.json`
- `batch_report.md`
- rolling updates after each job

## Phase 9: Tests

Goal:
Cover batch behavior quickly and safely with mocks.

Deliverables:

- batch queue tests
- resume tests
- report tests
- no real API calls

## Phase 10: Real Verification

Goal:
Confirm the final feature works in practice and does not break the old flow.

Deliverables:

- targeted batch test run
- relevant existing test run
- optional real two-link smoke verification if environment and API credentials allow
