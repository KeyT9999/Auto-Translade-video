# Requirement: Output Playback Speed Feature

This document outlines the requirement for adding final video playback speed control (1.0x, 1.1x, 1.2x, 1.3x) to the video-dubbing pipeline.

## 1. Objective
Enable users to speed up the final translated/dubbed output video. Both video and audio must be accelerated while remaining fully synchronized. Hardcoded or external subtitles (SRT, ASS, JSON) must also have their timestamps adjusted proportionally so that text remains aligned with the audio and video.

## 2. Scope & Target Playback Speeds
- **Supported Speeds**: `1.0`, `1.1`, `1.2`, `1.3`
- **Applicability**:
  - `subtitle_only` mode
  - `dub_audio` (TTS) mode
  - Batch queue operations (`batch_runner.py`)
  - Web UI configuration and pipeline runs
- **Default Speed**: `1.0` (standard playback speed, no changes to the current pipeline outputs).

## 3. Speed-up Strategy & Constraints
- **Timing Preservation**: The pipeline must perform all internal processing steps (ASR, translation, character bible detection, timeline rewriting, segment-level TTS synthesis, and original speed video merging/burning) at original speed. 
- **Last-step Adjustment**: The speed adjustment must occur as the **final step** immediately after rendering the complete video at its original speed.
  - This minimizes errors and avoids altering segment-level speech synthesis or timeline alignment logics.
  - This preserves the original speed render output for archiving if desired.
- **Robustness**: If a video lacks audio, the speed adjustment should still succeed (only adjusting video PTS, skipping audio speed filter).

## 4. Subtitle Timing Scaling
When speed $S > 1.0$, subtitle timeframes (in SRT, ASS, and transcript JSON files) must be rescaled:
$$\text{new\_start} = \frac{\text{old\_start}}{S}$$
$$\text{new\_end} = \frac{\text{old\_end}}{S}$$
$$\text{new\_duration} = \frac{\text{old\_duration}}{S}$$

Timestamps must be written to new files with the suffix corresponding to the applied speed (e.g., `transcript_vi_1.2x.srt`).

## 5. CLI & Web UI Settings
- **CLI Options**:
  - `pipeline_vi.py` accepts `--output-speed <float>`
  - `tools/batch_runner.py` accepts `--output-speed <float>`
- **Web UI Options**:
  - Setting dropdown select: `1.0x`, `1.1x`, `1.2x`, `1.3x`
  - Passes `output_playback_speed` payload parameter to API.

## 6. Config & Environment Variables
The following keys will be supported in `.env` and `config.py`:
- `OUTPUT_PLAYBACK_SPEED`: Default output playback speed.
- `OUTPUT_PLAYBACK_SPEED_OPTIONS`: Allowed speed choices (`1.0,1.1,1.2,1.3`).
- `APPLY_OUTPUT_SPEED_AFTER_RENDER`: Enable or disable the post-render speed-up block.
- `GENERATE_SPEED_ADJUSTED_SUBTITLES`: Enable generation of accelerated subtitle files.
- `OUTPUT_SPEED_KEEP_ORIGINAL_RENDER`: Keep the original speed video render file.
- `OUTPUT_SPEED_SUFFIX_FORMAT`: The suffix pattern for files (default `_{speed}x`).
