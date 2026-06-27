# Phase Plan: Output Playback Speed Feature

The implementation is structured into 4 sequential phases.

## Phase 1: Core Speed Module Development
- Create `src/output_speed.py`.
- Write validation and suffix logic.
- Implement the FFmpeg wrapper with robust no-audio handling.
- Write SRT, ASS, and JSON timestamp rescale logic.
- Create unit tests for these helper functions under `tests/test_output_speed.py`.

## Phase 2: Configuration & Pipeline Integration
- Update `config.py` and `.env.example` to read and validate playback speed configuration.
- Update `pipeline_vi.py` to add the `--output-speed` argument.
- Insert the execution step at the end of the pipeline.
- Propagate the speed-adjusted video file path to the publishing and report generators.
- Create integration tests verifying pipeline speed adjustments.

## Phase 3: CLI, Batch & Web UI Integration
- Update `tools/batch_runner.py` and `src/batch_runner.py` to add and propagate speed settings.
- Update Pydantic requests in `web_server.py`.
- Add the dropdown setting to `static/index.html` and attach it to API fetch payload.
- Update batch queue tests.

## Phase 4: Verification (Tests & Manual Runs)
- Run the full suite of automated tests (`pytest`) to ensure no regressions occur.
- Conduct a manual single video run at speed 1.2x.
- Conduct a manual batch queue run at speed 1.2x.
- Verify video/audio sync and subtitle timing alignment in outputs.
