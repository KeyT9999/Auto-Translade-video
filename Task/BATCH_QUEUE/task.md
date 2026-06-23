# Task Checklist: Batch Queue

## Phase 1: Documentation

- [x] Create `Task/BATCH_QUEUE/requirement.md`
- [x] Create `Task/BATCH_QUEUE/design.md`
- [x] Create `Task/BATCH_QUEUE/task.md`
- [x] Create `Task/BATCH_QUEUE/phase_plan.md`

## Phase 2: Config

- [x] Add batch env keys to `.env.example`
- [x] Add batch config parsing to `config.py`
- [x] Clamp batch concurrency to `1`

## Phase 3: Single-Video Integration

- [x] Add `PipelineResult` dataclass
- [x] Add reusable `run_single_video_pipeline(...)`
- [x] Preserve current `pipeline_vi.py` CLI behavior
- [x] Keep subtitle-only behavior unchanged

## Phase 4: Batch Models and Persistence

- [x] Add batch/job dataclasses or equivalent models
- [x] Add helpers to load/save `batch.json`
- [x] Add helpers to load/save `jobs/<nnn>/job.json`
- [x] Add helpers to write `session_link.txt` and `output_dir.txt`

## Phase 5: Batch Runner CLI

- [x] Create `tools/batch_runner.py`
- [x] Parse `--input`
- [x] Parse `--resume`
- [x] Parse `--retry-failed`
- [x] Parse `--retry-publish`
- [x] Parse `--dry-run`
- [x] Pass through relevant subtitle/publish options

## Phase 6: Sequential Execution

- [x] Validate `1-50` links
- [x] Create `batch_id`
- [x] Create batch folder
- [x] Create queue entries
- [x] Execute jobs strictly in order
- [x] Continue after failure by default
- [x] Stop when `--stop-on-error` is enabled
- [x] Delay between videos when configured

## Phase 7: Resume and Retry

- [x] Resume without rerunning success jobs
- [x] Retry failed jobs only
- [x] Retry publish-only without rerender
- [x] Recover interrupted `running` jobs safely

## Phase 8: Reporting

- [x] Generate `batch_report.json`
- [x] Generate `batch_report.md`
- [x] Refresh reports after each job
- [x] Include per-job output/error details

## Phase 9: Tests

- [x] Add `tests/test_batch_runner.py`
- [x] Add `tests/test_batch_resume.py`
- [x] Add `tests/test_batch_report.py`
- [x] Mock single-video pipeline calls
- [x] Verify sequential execution order
- [x] Verify resume/retry/report behavior

## Phase 10: Verification

- [x] Run targeted batch tests
- [x] Run relevant existing non-batch tests
- [x] Confirm single-video workflow still passes
