# Task List: Output Playback Speed Feature

This checklist tracks the progress of implementing output playback speed controls.

- [ ] Task 1: Create `src/output_speed.py`
  - [ ] Implement `validate_output_speed`
  - [ ] Implement `build_speed_suffix`
  - [ ] Implement `apply_playback_speed_to_video` with FFmpeg (and no-audio safety check)
  - [ ] Implement `adjust_srt_for_speed`
  - [ ] Implement `adjust_ass_for_speed`
  - [ ] Implement `adjust_transcript_json_for_speed`

- [ ] Task 2: Configure Environment Variables
  - [ ] Add speed options to `config.py`
  - [ ] Add environment variable examples to `.env.example`

- [ ] Task 3: Integrate into Pipeline (`pipeline_vi.py`)
  - [ ] Add CLI option `--output-speed`
  - [ ] Insert post-processing block after rendering is complete
  - [ ] Create timing-scaled sub/json files when speed > 1.0
  - [ ] Update report payload to include original vs. final video file paths
  - [ ] Ensure publishing module uses the final speed-adjusted video file

- [ ] Task 4: Integrate into Batch Queue
  - [ ] Add CLI option `--output-speed` to `tools/batch_runner.py`
  - [ ] Propagate speed option from CLI and JSON configurations into individual jobs in `src/batch_runner.py`
  - [ ] Include playback speed metadata in batch report files

- [ ] Task 5: Integrate into Web UI & API
  - [ ] Update Pydantic schemas in `web_server.py` (`PipelineRequest`, `BatchPipelineRequest`)
  - [ ] Route the request speeds into the execute functions
  - [ ] Add a playback speed dropdown to `static/index.html` UI panel
  - [ ] Include selection in API fetch payload

- [ ] Task 6: Implement Tests
  - [ ] Create `tests/test_output_speed.py` for unit tests (validation, SRT adjustment, JSON scaling, FFmpeg command mock)
  - [ ] Create `tests/test_output_speed_pipeline_integration.py` for full pipeline integration test
  - [ ] Create `tests/test_batch_output_speed.py` for batch queue options test

- [ ] Task 7: Manual Verification
  - [ ] Run a test on a single video with speed 1.2
  - [ ] Run a test batch queue with 2 videos with speed 1.2
