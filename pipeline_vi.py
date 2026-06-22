"""Vietnamese Video Dubbing Pipeline — CLI Entry Point.

Usage:
    python pipeline_vi.py                          # Reads VIDEO_URL from .env
    python pipeline_vi.py --url "https://..."      # Override with CLI arg
    python pipeline_vi.py --file video.mp4 --source-lang en
"""
import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pydub import AudioSegment as _ASeg

import config
from src.utils import setup_logging, ensure_dir
from src.downloader import download_video
from src.audio_extractor import extract_audio
from src.transcriber import transcribe, save_transcript
from src.synthesizer_vi import TTSSegmentError, is_valid_audio_file, synthesize_segment_vi
from src.audio_merger import merge_segments, fit_segments_to_timeline
from src.vocal_separator import separate_vocals
from src.video_merger import merge_video
from src.translate_pending import write_hint as _write_translate_pending_hint
from src.srt_generator import generate_srt
from src.content_generator import generate_content
from src.speaker_detector import detect_speakers, get_voice_id_for_segment

logger = setup_logging("pipeline_vi")

LANG_MAP = {
    "en": "en-US",
    "ja": "ja-JP",
    "zh": "zh-CN",
    "en-US": "en-US",
    "ja-JP": "ja-JP",
    "zh-CN": "zh-CN",
    "zh-HK": "zh-HK",
    "zh-TW": "zh-TW",
}


def _build_timing_guide(report: dict, segments: list[dict], tts_results: list[dict]) -> dict:
    """Build a timing guide JSON for Vietnamese audio."""
    guide = {
        "session_id": report["session_id"],
        "source_url": report["source_url"],
        "target_language": "vi-VN",
        "summary": {
            "total_segments": report["total_segments"],
            "original_duration": report["total_original_duration"],
            "vi_duration": report["total_tts_duration"],
            "ratio": round(report["total_tts_duration"] / report["total_original_duration"], 2)
                     if report["total_original_duration"] > 0 else 0,
            "segments_need_edit": 0,
            "segments_ok": 0,
        },
        "segments": [],
    }

    need_edit = 0
    for seg, tts in zip(segments, tts_results):
        actual_duration = float(tts.get("actual_duration", 0.0) or 0.0)
        diff = round(actual_duration - seg["duration"], 2)
        tts_status = str(tts.get("status", "")).lower().strip()

        if tts_status == "failed":
            status = "PENDING_TTS"
            need_edit += 1
        elif abs(diff) <= seg["duration"] * 0.3:
            status = "OK"
        elif diff > 0:
            status = "TOO_LONG"
            need_edit += 1
        else:
            status = "TOO_SHORT"
            need_edit += 1

        guide["segments"].append({
            "id": seg["id"],
            "text_original": seg["text"],
            "text_vi": seg.get("text_vi", ""),
            "start": seg["start"],
            "end": seg["end"],
            "original_duration": seg["duration"],
            "vi_duration": actual_duration,
            "diff_seconds": diff,
            "speed_adjusted": bool(tts.get("speed_adjusted", False)),
            "rate_applied": tts.get("rate_applied", ""),
            "status": status,
            "edit_hint": (
                tts.get("error", "Cần chạy lại TTS cho segment này.")
                if status == "PENDING_TTS"
                else "OK"
                if status == "OK"
                else f"VI {'dài' if diff > 0 else 'ngắn'} hơn {abs(diff):.1f}s"
            ),
        })

    guide["summary"]["segments_need_edit"] = need_edit
    guide["summary"]["segments_ok"] = report["total_segments"] - need_edit

    return guide


def _write_report_and_timing_guide(
    work_dir: str,
    report: dict,
    segments: list[dict],
    tts_results: list[dict],
) -> None:
    report_path = os.path.join(work_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    timing_guide = _build_timing_guide(report, segments, tts_results)
    timing_path = os.path.join(work_dir, "timing_guide.json")
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing_guide, f, ensure_ascii=False, indent=2)
    logger.info(f"Timing guide: {timing_path}")


def _get_default_vi_output_dir() -> str:
    """Get Vietnamese output directory: VIETNAMESE_OUTPUT_DIR or OUTPUT_DIR/VN."""
    if config.VIETNAMESE_OUTPUT_DIR:
        return config.VIETNAMESE_OUTPUT_DIR
    return os.path.join(config.OUTPUT_DIR, "VN")


def compute_translation_cache_hash(segments: list[dict], source_lang: str, translation_style: str) -> str:
    import hashlib
    content_str = json.dumps(segments, sort_keys=True, ensure_ascii=False)
    provider_model = config.TRANSLATION_PROVIDER + "_" + getattr(config, config.TRANSLATION_PROVIDER.upper() + "_MODEL", "unknown")
    hash_input = f"{source_lang}|vi|{content_str}|{translation_style}|{provider_model}"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def get_translation_from_cache(cache_hash: str) -> list[dict] | None:
    if not config.TRANSLATION_CACHE_ENABLED:
        return None
    cache_path = os.path.join(".cache", "translations", f"{cache_hash}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Cache hit! Loaded cached translation from {cache_path}")
            return data
        except Exception as e:
            logger.warning(f"Failed to load translation cache from {cache_path}: {e}")
    return None


def save_translation_to_cache(cache_hash: str, translated_segments: list[dict]):
    if not config.TRANSLATION_CACHE_ENABLED:
        return
    cache_dir = os.path.join(".cache", "translations")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{cache_hash}.json")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(translated_segments, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved translation to cache: {cache_path}")
    except Exception as e:
        logger.warning(f"Failed to save translation cache to {cache_path}: {e}")


def _first_nonempty_text(segment: dict, fields: list[str]) -> str:
    for field in fields:
        value = segment.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _synchronize_translation_segment(
    segment: dict,
    mode: str,
    ensure_default_speaker: bool = False,
) -> dict:
    """Keep translated fields aligned for validation, subtitle render, and TTS."""
    literal_text = _first_nonempty_text(
        segment,
        ["literal_vi", "text_vi", "subtitle_vi", "final_dub_vi", "dub_vi"],
    )
    subtitle_text = _first_nonempty_text(
        segment,
        ["subtitle_vi", "text_vi", "final_dub_vi", "dub_vi", "literal_vi"],
    )
    dub_text = _first_nonempty_text(
        segment,
        ["final_dub_vi", "dub_vi", "text_vi", "subtitle_vi", "literal_vi"],
    )

    canonical_text = subtitle_text if mode == "subtitle_only" else dub_text
    if not canonical_text:
        canonical_text = literal_text
    if not literal_text:
        literal_text = canonical_text

    updated = {
        **segment,
        "literal_vi": literal_text or "",
        "text_vi": canonical_text or "",
        "subtitle_vi": canonical_text or "",
        "dub_vi": canonical_text or "",
        "final_dub_vi": canonical_text or "",
    }

    if ensure_default_speaker:
        if not str(updated.get("speaker", "")).strip():
            updated["speaker"] = "NARRATOR"
        if not str(updated.get("speaker_gender", "")).strip():
            updated["speaker_gender"] = "neutral"
    elif str(updated.get("speaker", "")).strip() and not str(updated.get("speaker_gender", "")).strip():
        updated["speaker_gender"] = "neutral"

    updated.setdefault("timing_rewrite_applied", False)
    updated.setdefault("original_dub_vi", updated["dub_vi"])
    return updated


def _synchronize_translation_segments(
    segments: list[dict],
    mode: str,
    ensure_default_speaker: bool = False,
) -> list[dict]:
    return [
        _synchronize_translation_segment(
            segment,
            mode,
            ensure_default_speaker=ensure_default_speaker,
        )
        for segment in segments
    ]


def _load_json_if_exists(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load JSON from %s: %s", path, exc)
        return default


def _translation_text_snapshot(segments: list[dict], mode: str) -> dict[int, str]:
    if mode == "subtitle_only":
        fields = ["subtitle_vi", "text_vi", "dub_vi", "final_dub_vi", "literal_vi"]
    else:
        fields = ["final_dub_vi", "dub_vi", "text_vi", "subtitle_vi", "literal_vi"]
    snapshot: dict[int, str] = {}
    for segment in segments:
        snapshot[int(segment.get("id", 0) or 0)] = _first_nonempty_text(segment, fields)
    return snapshot


def _ask_voice_gender() -> str:
    """Ask user to choose male or female voice. Returns voice ID."""
    print("\n" + "=" * 40)
    print("Chọn giọng đọc / Choose voice:")
    print("  1. Nam (Male)")
    print("  2. Nữ (Female)")
    print("=" * 40)

    while True:
        choice = input("Nhập 1 hoặc 2 (Enter 1 or 2): ").strip()
        if choice == "1":
            voice_id = config.VIETNAMESE_VOICEID_MALE
            logger.info(f"Selected: Male voice ({voice_id})")
            return voice_id
        elif choice == "2":
            voice_id = config.VIETNAMESE_VOICEID_FEMALE
            logger.info(f"Selected: Female voice ({voice_id})")
            return voice_id
        else:
            print("Vui lòng nhập 1 hoặc 2.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vietnamese Video Dubbing Pipeline: EN/JA → VI")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--url", help="YouTube/TikTok video URL (default: VIDEO_URL from .env)")
    group.add_argument("--file", help="Local video file path")

    parser.add_argument(
        "--source-lang",
        default=config.DEFAULT_SOURCE_LANG,
        help=f"Source language: en, ja, zh, en-US, ja-JP, zh-CN, zh-HK, zh-TW (default: {config.DEFAULT_SOURCE_LANG})",
    )
    parser.add_argument(
        "--voice",
        choices=["male", "female"],
        default=None,
        help="Voice gender: male or female (if not set, will ask interactively)",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Skip final video merge (only produce audio + SRT)",
    )
    parser.add_argument(
        "--output-dir",
        default=_get_default_vi_output_dir(),
        help=f"Output directory (default: ANKO Project/VN)",
    )
    parser.add_argument(
        "--resume",
        metavar="WORK_DIR",
        help="Resume an existing work directory. Steps whose outputs already exist are skipped.",
    )
    parser.add_argument(
        "--from-step",
        choices=["translate"],
        default=None,
        help="When resuming, restart from a specific pipeline step (currently supports: translate).",
    )
    parser.add_argument(
        "--bg-mode",
        choices=["demucs", "duck", "none"],
        default="demucs",
        help="How to handle the original audio under the VI narration: "
             "'demucs' (default) runs vocal separation so only music/SFX remain — "
             "highest quality, ~7 min CPU per video. "
             "'duck' lowers the entire original_audio.wav by --bg-duck-db (default -12) "
             "and overlays VI on top — fast (no Demucs), original speech audible faintly. "
             "'none' merges VI on a silent base — legacy behavior, no original audio.",
    )
    parser.add_argument(
        "--bg-duck-db",
        type=float,
        default=-12.0,
        help="Gain (dB) applied to original audio in 'duck' mode. -12 dB ≈ 25%% volume "
             "(default), -6 dB ≈ 50%%, -20 dB ≈ 10%%. Ignored unless --bg-mode=duck.",
    )
    parser.add_argument(
        "--no-bg-music",
        action="store_true",
        help="Deprecated alias for --bg-mode=none. Kept for backwards compatibility.",
    )
    parser.add_argument(
        "--publish-youtube",
        action="store_true",
        help="Upload final video to YouTube",
    )
    parser.add_argument(
        "--publish-facebook",
        action="store_true",
        help="Upload final video to Facebook Page",
    )
    parser.add_argument(
        "--publish-only",
        choices=["youtube", "facebook"],
        default=None,
        help="Reuse an existing rendered video in --resume session and only publish it to the selected platform.",
    )
    parser.add_argument(
        "--pause-for-speakers",
        action="store_true",
        help="Pause pipeline after speaker detection for manual voice mapping",
    )
    parser.add_argument(
        "--burn-subtitles",
        action="store_true",
        help="Burn Vietnamese subtitles into the output video",
    )
    parser.add_argument(
        "--mode",
        choices=["dub_audio", "subtitle_only"],
        default="dub_audio",
        help="Output mode: 'dub_audio' (default) or 'subtitle_only'",
    )
    parser.add_argument(
        "--subtitle-only",
        action="store_true",
        help="Shortcut to set --mode=subtitle_only",
    )
    parser.add_argument(
        "--cover-original-subtitles",
        action="store_true",
        help="Cover/mask original subtitles in video with a dark overlay before burning Vietnamese subtitles",
    )
    parser.add_argument(
        "--subtitle-style",
        choices=["boxed", "plain"],
        default="plain",
        help="Subtitle style: 'plain' (outline only) or 'boxed' (text with background box)",
    )
    parser.add_argument(
        "--subtitle-font-size",
        type=int,
        default=None,
        help="Subtitle font size (overrides config default)",
    )
    parser.add_argument(
        "--mask-opacity",
        type=float,
        default=None,
        help="Opacity of the dark background cover mask (0.0 to 1.0)",
    )
    parser.add_argument(
        "--no-dub-audio",
        action="store_true",
        help="Skip TTS narration generation, keeping only original audio",
    )

    args = parser.parse_args()
    if args.subtitle_only:
        args.mode = "subtitle_only"

    if args.no_bg_music:
        args.bg_mode = "none"

    if not args.url and not args.file and not args.resume:
        if config.VIETNAMESE_VIDEO_URL:
            args.url = config.VIETNAMESE_VIDEO_URL
            logger.info(f"Using VIETNAMESE_VIDEO_URL from .env: {args.url}")
        elif config.VIDEO_URL:
            args.url = config.VIDEO_URL
            logger.info(f"Using VIDEO_URL from .env: {args.url}")
        else:
            parser.error("No video specified. Use --url, --file, --resume, or set VIETNAMESE_VIDEO_URL in .env")

    if args.from_step and not args.resume:
        parser.error("--from-step requires --resume")
    if args.publish_only and not args.resume:
        parser.error("--publish-only requires --resume")

    # Resolve voice ID: CLI flag > .env Voice_type > interactive prompt
    if args.publish_only:
        args.voice_id = ""
    elif args.mode == "subtitle_only" or args.no_dub_audio:
        # No voice prompt needed for subtitle-only / no-dub-audio mode
        if args.voice == "male":
            args.voice_id = config.VIETNAMESE_VOICEID_MALE
        elif args.voice == "female":
            args.voice_id = config.VIETNAMESE_VOICEID_FEMALE
        else:
            args.voice_id = ""
    else:
        if args.voice == "male":
            args.voice_id = config.VIETNAMESE_VOICEID_MALE
        elif args.voice == "female":
            args.voice_id = config.VIETNAMESE_VOICEID_FEMALE
        elif config.VOICE_TYPE == "male":
            args.voice_id = config.VIETNAMESE_VOICEID_MALE
            logger.info("Using VOICE_TYPE=male from .env")
        elif config.VOICE_TYPE == "female":
            args.voice_id = config.VIETNAMESE_VOICEID_FEMALE
            logger.info("Using VOICE_TYPE=female from .env")
        else:
            args.voice_id = _ask_voice_gender()

    return args


def _resolve_video(work_dir: str, url: str | None, file_path: str | None) -> str:
    """Locate the source video for this work_dir.

    Resume-friendly: if a prior run already downloaded/copied the source video
    into work_dir, reuse it instead of re-downloading. Skips any files whose
    name matches a pipeline output (dubbed_video*.mp4) so we don't mistake the
    rendered result for the source.

    If --file is passed, that takes precedence — useful when the user keeps
    the source outside work_dir.
    """
    if file_path:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Video file not found: {file_path}")
        return file_path

    video_exts = (".mp4", ".mkv", ".webm", ".mov", ".avi")
    output_prefixes = ("dubbed_video", "subtitled_video")
    for f in sorted(os.listdir(work_dir)):
        lower = f.lower()
        if not lower.endswith(video_exts):
            continue
        if any(lower.startswith(prefix) for prefix in output_prefixes):
            continue
        cached = os.path.join(work_dir, f)
        logger.info(f"Reusing existing video: {cached}")
        return cached

    if url:
        return download_video(url, work_dir)

    raise RuntimeError(
        f"No source video found in {work_dir} and no --url/--file given. "
        "Pass --file <path> on resume if the original is outside work_dir."
    )


def run_pipeline_vi(
    url: str | None,
    file_path: str | None,
    source_lang: str,
    voice_id: str,
    skip_video: bool,
    output_dir: str,
    resume_dir: str | None = None,
    bg_mode: str = "demucs",
    bg_duck_db: float = -12.0,
    publish_youtube: bool = False,
    publish_facebook: bool = False,
    pause_for_speakers: bool = False,
    speaker_map: dict | None = None,
    burn_subtitles: bool = False,
    mode: str = "dub_audio",
    cover_original_subtitles: bool = False,
    subtitle_style: str = "plain",
    subtitle_font_size: int | None = None,
    mask_opacity: float | None = None,
    no_dub_audio: bool = False,
    from_step: str | None = None,
) -> dict:
    start_time = time.time()

    lang_code = LANG_MAP.get(source_lang, source_lang)
    logger.info(f"Source language: {lang_code} → Vietnamese")

    # Resume an existing work_dir or create a new timestamped one
    if resume_dir:
        if not os.path.isdir(resume_dir):
            raise FileNotFoundError(f"Resume directory not found: {resume_dir}")
        work_dir = resume_dir
        folder_name = os.path.basename(os.path.normpath(work_dir))
        logger.info(f"Resuming work directory: {work_dir}")
        
        # Load mode from existing report.json if present
        report_path = os.path.join(work_dir, "report.json")
        if os.path.exists(report_path):
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    old_report = json.load(f)
                saved_mode = old_report.get("mode")
                if mode == "dub_audio" and not no_dub_audio and saved_mode:
                    mode = saved_mode
                    logger.info(f"Loaded mode '{mode}' from existing report.json")
                if not no_dub_audio and old_report.get("no_dub_audio"):
                    no_dub_audio = True
                    logger.info("Loaded no_dub_audio=true from existing report.json")
            except Exception as e:
                logger.warning(f"Could not load mode from existing report.json: {e}")
    else:
        folder_name = datetime.now().strftime("%Y%m%d%H%M%S") + "_vi"
        work_dir = ensure_dir(os.path.join(output_dir, folder_name))
        logger.info(f"Output folder: {work_dir}")

    subtitle_mode = mode == "subtitle_only" or no_dub_audio
    translation_mode = "subtitle_only" if subtitle_mode else mode

    transcript_orig_path = os.path.join(work_dir, "transcript_original.json")
    transcript_vi_path = os.path.join(work_dir, "transcript_vi.json")
    audio_path = os.path.join(work_dir, "original_audio.wav")

    # --- Step 1: Download or use local file ---
    logger.info("=" * 60)
    logger.info("STEP 1: Acquiring video")
    video_path = _resolve_video(work_dir, url, file_path)
    logger.info(f"Video: {video_path}")

    # --- Step 2: Extract audio ---
    logger.info("=" * 60)
    logger.info("STEP 2: Extracting audio")
    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
        logger.info(f"Reusing existing audio: {audio_path}")
    else:
        extract_audio(video_path, audio_path)

    # --- Step 2.5: Resolve background track for the dub merge ---
    background_path: str | None = None
    background_gain_db: float = 0.0
    if mode == "dub_audio" and not subtitle_mode:
        if bg_mode == "demucs":
            logger.info("=" * 60)
            logger.info("STEP 2.5: Separating vocals from original audio (Demucs)")
            sep = separate_vocals(audio_path, work_dir)
            background_path = sep.get("no_vocals")
            if background_path is None:
                logger.warning(
                    "Vocal separation unavailable — dubbed audio will use a silent base"
                )
        elif bg_mode == "duck":
            logger.info("=" * 60)
            logger.info(
                f"STEP 2.5: Ducking original audio by {bg_duck_db:+.1f} dB "
                "(no vocal separation)"
            )
            background_path = audio_path
            background_gain_db = bg_duck_db
        elif bg_mode == "none":
            logger.info("STEP 2.5 skipped: --bg-mode=none, dubbed audio uses silent base")
    else:
        logger.info("STEP 2.5 skipped: subtitle-only mode or no_dub_audio is enabled")

    # --- Step 3: Speech-to-Text (ASR) ---
    logger.info("=" * 60)
    logger.info("STEP 3: Transcribing audio (ASR)")
    if os.path.exists(transcript_orig_path):
        logger.info(f"Reusing existing transcript: {transcript_orig_path}")
        with open(transcript_orig_path, encoding="utf-8") as f:
            segments = json.load(f)
        logger.info(f"Loaded {len(segments)} segments from cache")
    else:
        segments = transcribe(audio_path, lang_code)
        save_transcript(segments, transcript_orig_path)
        generate_srt(segments, os.path.join(work_dir, "transcript_original.srt"), text_field="text")
        logger.info(f"Transcribed {len(segments)} segments")

    # --- Step 4: Translate to Vietnamese ---
    logger.info("=" * 60)
    logger.info("STEP 4: Translating to Vietnamese")
    video_context_path = os.path.join(work_dir, "video_context.json")
    character_bible_path = os.path.join(work_dir, "character_bible.json")
    glossary_path = os.path.join(work_dir, "glossary.json")
    quality_report_path = os.path.join(work_dir, "translation_quality_report.json")
    repair_report_path = os.path.join(work_dir, "translation_repair_report.json")

    from src.character_profiler import build_character_bible, sanitize_character_bible
    from src.context_builder import build_video_context
    contextual_translator_module = importlib.import_module("src.contextual_translator")
    translate_segments_contextual = contextual_translator_module.translate_segments_contextual
    from src.glossary_builder import build_glossary
    from src.glossary_enforcer import apply_glossary_to_segments, sanitize_glossary
    from src.subtitle_polisher import polish_subtitle_segments
    from src.subtitle_group_rewriter import rewrite_subtitle_groups
    from src.timeline_rewriter import rewrite_timeline
    from src.translation_repair import repair_translation
    from src.translation_validator import (
        filter_repairable_issues,
        has_blocking_errors,
        validate_translation,
    )

    def _persist_json_artifact(path: str, payload: dict) -> None:
        if not payload:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to persist JSON artifact %s: %s", path, exc)

    video_context = _load_json_if_exists(video_context_path, {})
    glossary = sanitize_glossary(_load_json_if_exists(glossary_path, {}))
    character_bible = sanitize_character_bible(_load_json_if_exists(character_bible_path, {}))
    if glossary:
        _persist_json_artifact(glossary_path, glossary)
    if character_bible:
        _persist_json_artifact(character_bible_path, character_bible)
    rerun_translation = from_step == "translate"
    translation_source = "existing" if os.path.exists(transcript_vi_path) and not rerun_translation else "contextual"
    cache_hash = None

    translation_pending_error_cls = getattr(contextual_translator_module, "TranslationPendingError", None)

    def _is_translation_pending_error(exc: Exception) -> bool:
        return isinstance(translation_pending_error_cls, type) and isinstance(exc, translation_pending_error_cls)

    def _extract_failed_ranges(exc: Exception) -> list[str]:
        failed_windows = getattr(exc, "failed_windows", None)
        if not isinstance(failed_windows, list):
            return []

        failed_ranges: list[str] = []
        for item in failed_windows:
            if isinstance(item, dict):
                range_key = item.get("range")
                if range_key:
                    failed_ranges.append(str(range_key))
        return failed_ranges

    def finalize_translation_segments(candidate_segments: list[dict]) -> tuple[list[dict], dict]:
        def _apply_subtitle_quality_passes(pass_segments: list[dict]) -> list[dict]:
            pass_segments = apply_glossary_to_segments(pass_segments, glossary)
            if translation_mode == "subtitle_only":
                pass_segments = polish_subtitle_segments(pass_segments, character_bible)
                pass_segments = _synchronize_translation_segments(
                    pass_segments,
                    translation_mode,
                    ensure_default_speaker=True,
                )
                pass_segments = apply_glossary_to_segments(pass_segments, glossary)
            return pass_segments

        candidate_segments = _synchronize_translation_segments(
            candidate_segments,
            translation_mode,
            ensure_default_speaker=subtitle_mode,
        )
        candidate_segments = _apply_subtitle_quality_passes(candidate_segments)

        logger.info("Validating translation...")
        quality_report = validate_translation(
            candidate_segments,
            quality_report_path,
            mode=translation_mode,
            source_language=lang_code,
            glossary=glossary,
        )

        max_rounds = getattr(config, "TRANSLATION_MAX_REPAIR_ROUNDS", 2)
        previous_bad_segments = quality_report["bad_segments"]
        for round_num in range(1, max_rounds + 1):
            repairable_issues = filter_repairable_issues(quality_report["issues"])
            if quality_report["bad_segments"] == 0 or not repairable_issues:
                break

            targeted_ids = {issue["id"] for issue in repairable_issues if issue.get("id", 0) > 0}
            before_snapshot = _translation_text_snapshot(candidate_segments, translation_mode)
            logger.info(
                "[Round %s/%s] Repairing %s blocking segment(s).",
                round_num,
                max_rounds,
                len(targeted_ids),
            )
            candidate_segments = repair_translation(
                candidate_segments,
                repairable_issues,
                video_context,
                glossary,
                character_bible,
                repair_report_path,
            )
            candidate_segments = _synchronize_translation_segments(
                candidate_segments,
                translation_mode,
                ensure_default_speaker=subtitle_mode,
            )
            candidate_segments = _apply_subtitle_quality_passes(candidate_segments)
            after_snapshot = _translation_text_snapshot(candidate_segments, translation_mode)
            changed_count = sum(
                1 for seg_id in targeted_ids if before_snapshot.get(seg_id) != after_snapshot.get(seg_id)
            )

            logger.info("Re-validating translation quality post-repair (Round %s)...", round_num)
            quality_report = validate_translation(
                candidate_segments,
                quality_report_path,
                mode=translation_mode,
                source_language=lang_code,
                glossary=glossary,
            )
            current_bad_segments = quality_report["bad_segments"]

            if changed_count == 0:
                logger.warning("Repair round %s made no text changes; stopping repair loop.", round_num)
                break
            if current_bad_segments >= previous_bad_segments:
                logger.warning(
                    "Repair round %s did not reduce blocking segments (%s -> %s); stopping repair loop.",
                    round_num,
                    previous_bad_segments,
                    current_bad_segments,
                )
                break
            previous_bad_segments = current_bad_segments

        if translation_mode == "subtitle_only":
            logger.info("Skipping timeline rewriter in subtitle-only mode.")
        else:
            logger.info("Running timeline rewriter...")
            candidate_segments = rewrite_timeline(candidate_segments, video_context, character_bible)
            candidate_segments = _synchronize_translation_segments(
                candidate_segments,
                translation_mode,
                ensure_default_speaker=subtitle_mode,
            )
            candidate_segments = _apply_subtitle_quality_passes(candidate_segments)

        if translation_mode == "subtitle_only":
            candidate_segments = rewrite_subtitle_groups(candidate_segments)
            candidate_segments = _synchronize_translation_segments(
                candidate_segments,
                translation_mode,
                ensure_default_speaker=True,
            )
            candidate_segments = _apply_subtitle_quality_passes(candidate_segments)

        final_report = validate_translation(
            candidate_segments,
            quality_report_path,
            mode=translation_mode,
            source_language=lang_code,
            glossary=glossary,
        )
        return candidate_segments, final_report

    if os.path.exists(transcript_vi_path) and not rerun_translation:
        logger.info(f"Reusing existing translation: {transcript_vi_path}")
        with open(transcript_vi_path, encoding="utf-8") as f:
            segments = json.load(f)
    else:
        try:
            if rerun_translation and os.path.exists(transcript_vi_path):
                logger.info("Re-running translation from STEP 4 because --from-step=translate was requested.")
            logger.info("Running automatic contextual translation...")
            if not video_context:
                logger.info("Building context profiles...")
                video_context = build_video_context(segments, video_context_path)
            if not glossary:
                glossary = build_glossary(segments, video_context, glossary_path)
            if not character_bible:
                character_bible = build_character_bible(segments, video_context, character_bible_path)

            translation_style = video_context.get("translation_style", "spoken Vietnamese")
            cache_hash = compute_translation_cache_hash(segments, source_lang, translation_style)
            cached_segments = get_translation_from_cache(cache_hash)
            if cached_segments is not None:
                logger.info("Translation cache hit. Reusing cached contextual translation.")
                segments = cached_segments
                translation_source = "cache"
            else:
                segments = translate_segments_contextual(
                    segments,
                    video_context,
                    glossary,
                    character_bible,
                    source_lang,
                    work_dir=work_dir,
                )
                translation_source = "contextual"
            logger.info("Automatic contextual translation complete.")
        except Exception as e:
            failed_ranges = _extract_failed_ranges(e)
            if _is_translation_pending_error(e):
                logger.warning("Automatic contextual translation incomplete: %s", e)
            else:
                logger.error("Automatic contextual translation failed: %s", e)
            _write_translate_pending_hint(
                work_dir,
                "vi-VN",
                source_lang,
                mode=mode,
                failed_ranges=failed_ranges or None,
            )
            logger.warning("Translation pending - see TRANSLATE_PENDING.txt in work dir")
            return {
                "status": "translate_pending",
                "work_dir": work_dir,
                "failed_ranges": failed_ranges or None,
            }
            logger.warning("Translation pending â€” see TRANSLATE_PENDING.txt in work dir")
            return {
                "status": "translate_pending",
                "work_dir": work_dir,
                "failed_ranges": failed_ranges or None,
            }
            logger.error(f"Automatic contextual translation failed: {e}")
            try:
                logger.info("Falling back to old translation...")
                from src.translator import translate_segments

                segments = translate_segments(segments, source_lang)
                translation_source = "legacy_fallback"
                logger.info("Fallback translation complete.")
            except Exception as ex:
                logger.error(f"Fallback translation also failed: {ex}")
                logger.info("Falling back to manual translation mode...")
                _write_translate_pending_hint(work_dir, "vi-VN", source_lang, mode=mode)
                logger.warning("Translation pending — see TRANSLATE_PENDING.txt in work dir")
                return {"status": "translate_pending", "work_dir": work_dir}

    try:
        segments, quality_report = finalize_translation_segments(segments)
        if has_blocking_errors(quality_report):
            if translation_source in {"contextual", "cache"}:
                raise RuntimeError("Contextual translation still has blocking errors after repair.")
            if translation_source == "existing":
                raise RuntimeError("Existing translation still has blocking errors after repair.")
            raise RuntimeError("Fallback translation still has blocking errors after repair.")

        if cache_hash and translation_source in {"contextual", "cache"}:
            save_translation_to_cache(cache_hash, segments)
    except Exception as quality_exc:
        logger.error("Translation quality flow failed: %s", quality_exc)
        _write_translate_pending_hint(work_dir, "vi-VN", source_lang, mode=mode)
        logger.warning("Translation pending - see TRANSLATE_PENDING.txt in work dir")
        return {"status": "translate_pending", "work_dir": work_dir}
        logger.warning("Translation pending â€” see TRANSLATE_PENDING.txt in work dir")
        return {"status": "translate_pending", "work_dir": work_dir}
        if translation_source in {"contextual", "cache"}:
            try:
                logger.info("Falling back to old translation after contextual QA failure...")
                from src.translator import translate_segments

                fallback_segments = translate_segments(segments, source_lang)
                translation_source = "legacy_fallback"
                segments, quality_report = finalize_translation_segments(fallback_segments)
                if has_blocking_errors(quality_report):
                    raise RuntimeError("Fallback translation still has blocking errors after repair.")
                logger.info("Fallback translation passed subtitle render flow.")
            except Exception as fallback_exc:
                logger.error("Fallback translation after QA failure also failed: %s", fallback_exc)
                logger.info("Falling back to manual translation mode...")
                _write_translate_pending_hint(work_dir, "vi-VN", source_lang, mode=mode)
                logger.warning("Translation pending — see TRANSLATE_PENDING.txt in work dir")
                return {"status": "translate_pending", "work_dir": work_dir}
        else:
            logger.info("Falling back to manual translation mode...")
            _write_translate_pending_hint(work_dir, "vi-VN", source_lang, mode=mode)
            logger.warning("Translation pending — see TRANSLATE_PENDING.txt in work dir")
            return {"status": "translate_pending", "work_dir": work_dir}

    segments = _synchronize_translation_segments(
        segments,
        translation_mode,
        ensure_default_speaker=subtitle_mode,
    )
    with open(transcript_vi_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    generate_srt(
        segments,
        os.path.join(work_dir, "transcript_vi.srt"),
        text_field="subtitle_vi",
    )
    translate_pending_path = os.path.join(work_dir, "TRANSLATE_PENDING.txt")
    if os.path.exists(translate_pending_path):
        try:
            os.remove(translate_pending_path)
            logger.info("Removed stale translation pending hint: %s", translate_pending_path)
        except OSError as exc:
            logger.warning("Could not remove stale translation pending hint %s: %s", translate_pending_path, exc)

    # --- Step 4.5: Speaker / Character Detection ---
    if subtitle_mode:
        logger.info("Skipping speaker detection in subtitle-only/no-dub-audio mode.")
        segments = _synchronize_translation_segments(
            segments,
            translation_mode,
            ensure_default_speaker=True,
        )
        with open(transcript_vi_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)
    else:
        logger.info("=" * 60)
        logger.info("STEP 4.5: Detecting speakers (character identification)")
        speaker_path = os.path.join(work_dir, "transcript_vi.json")  # overwrite with speaker info
        # Only re-detect if speakers haven't been assigned yet (resume-friendly)
        if segments and "speaker" not in segments[0]:
            segments = detect_speakers(segments)
            # Persist updated transcript with speaker fields
            with open(speaker_path, "w", encoding="utf-8") as f:
                json.dump(segments, f, ensure_ascii=False, indent=2)
            logger.info(f"Speaker info written to: {speaker_path}")
        else:
            logger.info("Speaker info already present in transcript — skipping detection.")

    # Check if we should pause for manual speaker configuration
    if pause_for_speakers and not subtitle_mode:
        voice_map_path = os.path.join(work_dir, "voice_character_map.json")
        if not os.path.exists(voice_map_path) and not speaker_map:
            logger.warning("Pipeline paused: Waiting for manual speaker voice assignment in UI.")
            return {"status": "speaker_pending", "work_dir": work_dir}

    # --- Step 5: TTS for each segment (LucyLab API) ---
    tts_results = []
    tts_cached_ids: list[int] = []
    tts_retried_ids: list[int] = []
    tts_new_ids: list[int] = []
    failed_tts_segments: list[dict] = []
    pending_tts_path = os.path.join(work_dir, "tts_pending_segments.json")
    tts_cache_dir = os.path.join(work_dir, "tts_segments")
    if mode == "dub_audio" and not subtitle_mode:
        logger.info("=" * 60)
        logger.info("STEP 5: Synthesizing Vietnamese audio (LucyLab TTS)")
        seg_dir = ensure_dir(os.path.join(work_dir, "segments"))
        tts_cache_dir = ensure_dir(os.path.join(work_dir, "tts_segments"))

        # Save speaker_map to voice_character_map.json if provided
        if speaker_map:
            voice_map_path = os.path.join(work_dir, "voice_character_map.json")
            try:
                with open(voice_map_path, "w", encoding="utf-8") as f:
                    json.dump(speaker_map, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved custom speaker map to {voice_map_path}")
            except Exception as e:
                logger.error(f"Failed to save custom speaker map: {e}")

        # Load custom voice character map if exists in work_dir
        voice_map_path = os.path.join(work_dir, "voice_character_map.json")
        voice_map = {}
        if os.path.exists(voice_map_path):
            try:
                with open(voice_map_path, "r", encoding="utf-8") as f:
                    voice_map = json.load(f)
                logger.info(f"Loaded custom voice map: {voice_map}")
            except Exception as e:
                logger.error(f"Failed to load custom voice map: {e}")

        for seg in segments:
            seg_path = os.path.join(seg_dir, f"seg_{seg['id']:03d}.wav")
            cache_path = os.path.join(tts_cache_dir, f"segment_{seg['id']:04d}.wav")

            if not os.path.exists(cache_path) and is_valid_audio_file(seg_path):
                shutil.copy2(seg_path, cache_path)
                logger.info(f"  Segment {seg['id']}: promoted legacy cache -> {cache_path}")

            seg_voice_id = get_voice_id_for_segment(seg, voice_id, voice_map=voice_map)
            speaker_label = seg.get("speaker", "")
            gender_label = seg.get("speaker_gender", "")
            if speaker_label:
                mapped_by = "default fallback"
                if voice_map and speaker_label in voice_map:
                    mapped_by = "custom UI map"
                elif hasattr(config, "VOICE_CHARACTER_MAP") and config.VOICE_CHARACTER_MAP and speaker_label in config.VOICE_CHARACTER_MAP:
                    mapped_by = "config map"
                elif speaker_label == "NARRATOR" and getattr(config, "VOICE_NARRATOR", ""):
                    mapped_by = "narrator fallback"

                logger.info(
                    f"  Segment {seg['id']} [{speaker_label}/{gender_label}]: "
                    f"voice_id={seg_voice_id} ({mapped_by})"
                )

            if is_valid_audio_file(cache_path):
                shutil.copy2(cache_path, seg_path)
                cached = _ASeg.from_wav(cache_path)
                result = {
                    "path": seg_path,
                    "actual_duration": round(len(cached) / 1000.0, 3),
                    "speed_adjusted": False,
                    "rate_applied": "cached",
                    "provider": getattr(config, "TTS_PROVIDER", "lucylab"),
                    "voice_id": seg_voice_id,
                    "job_id": None,
                    "audio_url": None,
                    "retry_count": 0,
                    "status": "cached",
                    "cache_path": cache_path,
                }
                tts_cached_ids.append(int(seg["id"]))
                logger.info(
                    f"  Segment {seg['id']}: cached ({result['actual_duration']:.1f}s, "
                    f"target {seg['duration']:.1f}s)"
                )
            else:
                try:
                    result = synthesize_segment_vi(
                        text_vi=seg["text_vi"],
                        output_path=cache_path,
                        target_duration=seg["duration"],
                        voice_id=seg_voice_id,
                    )
                    shutil.copy2(cache_path, seg_path)
                    result["path"] = seg_path
                    result["status"] = "generated"
                    result["cache_path"] = cache_path
                    if int(result.get("retry_count", 0) or 0) > 0:
                        tts_retried_ids.append(int(seg["id"]))
                    else:
                        tts_new_ids.append(int(seg["id"]))
                    logger.info(
                        f"  Segment {seg['id']}: {result['actual_duration']:.1f}s "
                        f"(target: {seg['duration']:.1f}s, speed: {result.get('rate_applied', '1.0x')}, "
                        f"retries: {result.get('retry_count', 0)})"
                    )
                except TTSSegmentError as exc:
                    error_message = str(exc)
                    logger.error(f"  Segment {seg['id']} TTS failed after retries: {error_message}")
                    failure = {
                        "id": int(seg["id"]),
                        "text_vi": seg.get("text_vi", ""),
                        "voice_id": seg_voice_id,
                        "provider": exc.provider,
                        "job_id": exc.job_id,
                        "audio_url": exc.audio_url,
                        "error": error_message,
                    }
                    failed_tts_segments.append(failure)
                    result = {
                        "path": "",
                        "actual_duration": 0.0,
                        "speed_adjusted": False,
                        "rate_applied": "failed",
                        "provider": exc.provider,
                        "voice_id": seg_voice_id,
                        "job_id": exc.job_id,
                        "audio_url": exc.audio_url,
                        "retry_count": exc.attempts,
                        "status": "failed",
                        "cache_path": cache_path,
                        "error": error_message,
                    }
            tts_results.append(result)

        if failed_tts_segments:
            pending_payload = {
                "status": "partial_failed",
                "failed_segments": failed_tts_segments,
            }
            with open(pending_tts_path, "w", encoding="utf-8") as f:
                json.dump(pending_payload, f, ensure_ascii=False, indent=2)

            logger.warning(
                "TTS incomplete: %s segment(s) failed after retries. Resume will retry only those segments.",
                len(failed_tts_segments),
            )

            elapsed = time.time() - start_time
            report = {
                "status": "partial_failed",
                "session_id": folder_name,
                "mode": mode,
                "no_dub_audio": no_dub_audio,
                "subtitle_burned": burn_subtitles,
                "cover_original_subtitles": cover_original_subtitles,
                "subtitle_style": subtitle_style,
                "source_url": url,
                "source_language": lang_code,
                "target_language": "vi-VN",
                "voice_id": voice_id,
                "total_segments": len(segments),
                "total_original_duration": round(sum(s["duration"] for s in segments), 3),
                "total_tts_duration": round(sum(float(r.get("actual_duration", 0.0) or 0.0) for r in tts_results), 3),
                "segments_speed_adjusted": sum(1 for r in tts_results if r.get("speed_adjusted")),
                "processing_time_seconds": round(elapsed, 1),
                "output_dir": work_dir,
                "published_urls": {"youtube": None, "facebook": None},
                "tts_summary": {
                    "cached_segment_ids": tts_cached_ids,
                    "retried_segment_ids": tts_retried_ids,
                    "new_segment_ids": tts_new_ids,
                    "failed_segment_ids": [item["id"] for item in failed_tts_segments],
                    "failed_segments": failed_tts_segments,
                },
                "tts_segments": tts_results,
                "files": {
                    "original_audio": audio_path,
                    "transcript_original_json": os.path.join(work_dir, "transcript_original.json"),
                    "transcript_original_srt": os.path.join(work_dir, "transcript_original.srt"),
                    "transcript_vi_json": os.path.join(work_dir, "transcript_vi.json"),
                    "transcript_vi_srt": os.path.join(work_dir, "transcript_vi.srt"),
                    "transcript_vi_ass": None,
                    "audio_vi_full": None,
                    "dubbed_video": None,
                    "thumbnails": [],
                    "youtube_metadata": None,
                    "tts_pending_segments": pending_tts_path,
                    "tts_segment_dir": tts_cache_dir,
                },
            }
            _write_report_and_timing_guide(work_dir, report, segments, tts_results)
            return report

        if os.path.exists(pending_tts_path):
            os.remove(pending_tts_path)
    else:
        logger.info("Skipping narration synthesis in subtitle-only/no-dub-audio mode.")
        for seg in segments:
            tts_results.append({
                "path": "",
                "actual_duration": seg["duration"],
                "speed_adjusted": False,
                "rate_applied": "none",
                "status": "skipped",
            })

    # --- Step 6: Slow down + Fit-to-timeline + Merge audio ---
    merged_audio_path = os.path.join(work_dir, "audio_vi_full.wav")
    if mode == "dub_audio" and not subtitle_mode:
        logger.info("=" * 60)
        slow_factor = config.AUDIO_SLOW_FACTOR
        total_duration = max(seg["end"] for seg in segments) + 1.0 if segments else 0

        if slow_factor < 1.0:
            slow_pct = round((1.0 - slow_factor) * 100)
            logger.info(f"STEP 6a: Slowing segments {slow_pct}% (atempo={slow_factor})")
            slow_dir = ensure_dir(os.path.join(work_dir, f"segments_slow{slow_pct}"))
            for seg in segments:
                src = os.path.join(seg_dir, f"seg_{seg['id']:03d}.wav")
                dst = os.path.join(slow_dir, f"seg_{seg['id']:03d}.wav")
                if os.path.exists(src):
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", src, "-filter:a", f"atempo={slow_factor}", dst],
                        capture_output=True, text=True,
                    )
            pre_fit_dir = slow_dir
        else:
            pre_fit_dir = seg_dir

        logger.info("STEP 6b: Fitting segments to timeline (avoid overlap)")
        fit_dir = ensure_dir(os.path.join(work_dir, "segments_fit"))
        fit_adjustments = fit_segments_to_timeline(segments, pre_fit_dir, fit_dir)

        fit_log_path = os.path.join(work_dir, "fit_adjustments.json")
        with open(fit_log_path, "w", encoding="utf-8") as f:
            json.dump(fit_adjustments, f, ensure_ascii=False, indent=2)

        logger.info("STEP 6c: Merging audio segments")
        merge_segments(
            segments, fit_dir, merged_audio_path, total_duration,
            background_path=background_path,
            background_gain_db=background_gain_db,
        )
    else:
        logger.info("Skipping audio-timeline processing in subtitle-only/no-dub-audio mode.")

    # --- Step 7: Merge video (optional) ---
    dubbed_video_path = None
    if not skip_video:
        logger.info("=" * 60)
        if subtitle_mode:
            logger.info("STEP 7: Creating subtitled video (original audio preserved)")
            subtitled_video_path = os.path.join(work_dir, "subtitled_video.mp4")
            if burn_subtitles:
                # Always generate SRT for compatibility
                srt_path = os.path.join(work_dir, "transcript_vi.srt")

                # Generate ASS subtitles for better rendering
                from src.subtitle_renderer import generate_ass_subtitles, render_video_with_cover
                ass_path = os.path.join(work_dir, "transcript_vi.ass")
                ass_style_config = {
                    "style": subtitle_style,
                    "font_name": config.SUBTITLE_FONT_NAME,
                    "font_size": subtitle_font_size if subtitle_font_size is not None else config.SUBTITLE_FONT_SIZE,
                    "outline_size": config.SUBTITLE_OUTLINE_SIZE,
                    "shadow_size": config.SUBTITLE_SHADOW_SIZE,
                    "box_opacity": config.SUBTITLE_BOX_OPACITY,
                    "margin_bottom": config.SUBTITLE_MARGIN_BOTTOM,
                    "max_chars_per_line": config.SUBTITLE_MAX_CHARS_PER_LINE,
                }
                try:
                    generate_ass_subtitles(segments, ass_path, ass_style_config)
                    cover_cfg = {
                        "cover_original_subtitles": cover_original_subtitles,
                        "mask_y_percent": config.SUBTITLE_MASK_Y_PERCENT,
                        "mask_height_percent": config.SUBTITLE_MASK_HEIGHT_PERCENT,
                        "mask_opacity": mask_opacity if mask_opacity is not None else config.SUBTITLE_MASK_OPACITY,
                        "mask_extra_height_percent": config.SUBTITLE_MASK_EXTRA_HEIGHT_PERCENT,
                        "mask_extra_opacity": config.SUBTITLE_MASK_EXTRA_OPACITY,
                    }
                    render_video_with_cover(video_path, ass_path, subtitled_video_path, cover_cfg)
                except Exception as e:
                    logger.warning(f"ASS renderer failed ({e}), falling back to SRT burn...")
                    from src.video_merger import burn_subtitles_to_video
                    burn_subtitles_to_video(video_path, srt_path, subtitled_video_path)
            else:
                shutil.copy2(video_path, subtitled_video_path)
                logger.info(f"Copying original video to output: {subtitled_video_path}")
            dubbed_video_path = subtitled_video_path
        else:
            logger.info("STEP 7: Creating dubbed video")
            dubbed_video_path = os.path.join(work_dir, "dubbed_video.mp4")
            srt_path = os.path.join(work_dir, "transcript_vi.srt") if burn_subtitles else None
            merge_video(video_path, merged_audio_path, dubbed_video_path, srt_path=srt_path)

    # --- Step 8: Generate thumbnails + YouTube metadata ---
    content_result = {"thumbnails": [], "metadata": {}}
    if (config.GEMINI_ENABLED and config.GOOGLE_API_KEY) or config.GROQ_API_KEY:
        logger.info("=" * 60)
        logger.info("STEP 8: Generating thumbnails & YouTube metadata")
        try:
            content_result = generate_content(
                segments=segments,
                target_lang="vi-VN",
                source_url=url,
                output_dir=work_dir,
                api_key=config.GOOGLE_API_KEY if config.GEMINI_ENABLED else "",
                image_model_id=config.IMAGE_MODEL_ID,
                content_model_id=config.CONTENT_MODEL_ID,
            )
            logger.info(f"  Thumbnail prompts: {content_result.get('thumbnail_prompts_file', 'N/A')}")
            logger.info(f"  Metadata: {content_result.get('metadata_file', 'N/A')}")
        except Exception as e:
            logger.error(f"Content generation failed (non-fatal): {e}")
    else:
        logger.info("Skipping thumbnail/metadata generation (no enabled Gemini or Groq provider available)")

    # --- Step 9: Publish Video ---
    youtube_url = None
    facebook_url = None
    publish_status = {"youtube": "not_requested", "facebook": "not_requested"}
    publish_error = {}
    if dubbed_video_path and os.path.exists(dubbed_video_path):
        meta_data = content_result.get("metadata", {})
        title = meta_data.get("title", "Dubbed Video")
        description = meta_data.get("description", "Auto-dubbed video")
        tags = meta_data.get("hashtags", [])

        if publish_youtube:
            logger.info("=" * 60)
            logger.info("STEP 9a: Publishing to YouTube")
            from src.publisher import publish_to_youtube_detailed
            youtube_result = publish_to_youtube_detailed(dubbed_video_path, title, description, tags)
            youtube_url = youtube_result.get("url")
            publish_status["youtube"] = "success" if youtube_result.get("success") else "failed"
            if youtube_result.get("error"):
                publish_error["youtube"] = youtube_result["error"]

        if publish_facebook:
            logger.info("=" * 60)
            logger.info("STEP 9b: Publishing to Facebook")
            from src.publisher import publish_to_facebook_detailed
            facebook_result = publish_to_facebook_detailed(dubbed_video_path, title, description)
            facebook_url = facebook_result.get("url")
            publish_status["facebook"] = "success" if facebook_result.get("success") else "failed"
            if facebook_result.get("error"):
                publish_error["facebook"] = facebook_result["error"]

    # --- Generate report ---
    elapsed = time.time() - start_time
    report = {
        "status": "success",
        "session_id": folder_name,
        "mode": mode,
        "no_dub_audio": no_dub_audio,
        "subtitle_burned": burn_subtitles,
        "cover_original_subtitles": cover_original_subtitles,
        "subtitle_style": subtitle_style,
        "source_url": url,
        "source_language": lang_code,
        "target_language": "vi-VN",
        "voice_id": voice_id,
        "total_segments": len(segments),
        "total_original_duration": round(sum(s["duration"] for s in segments), 3),
        "total_tts_duration": round(sum(float(r.get("actual_duration", 0.0) or 0.0) for r in tts_results), 3),
        "segments_speed_adjusted": sum(1 for r in tts_results if r.get("speed_adjusted")),
        "processing_time_seconds": round(elapsed, 1),
        "output_dir": work_dir,
        "published_urls": {
            "youtube": youtube_url,
            "facebook": facebook_url,
        },
        "publish_status": publish_status,
        "publish_error": publish_error,
        "tts_summary": {
            "cached_segment_ids": tts_cached_ids,
            "retried_segment_ids": tts_retried_ids,
            "new_segment_ids": tts_new_ids,
            "failed_segment_ids": [item["id"] for item in failed_tts_segments],
            "failed_segments": failed_tts_segments,
        },
        "tts_segments": tts_results,
        "files": {
            "original_audio": audio_path,
            "transcript_original_json": os.path.join(work_dir, "transcript_original.json"),
            "transcript_original_srt": os.path.join(work_dir, "transcript_original.srt"),
            "transcript_vi_json": os.path.join(work_dir, "transcript_vi.json"),
            "transcript_vi_srt": os.path.join(work_dir, "transcript_vi.srt"),
            "transcript_vi_ass": os.path.join(work_dir, "transcript_vi.ass") if (subtitle_mode and burn_subtitles) else None,
            "audio_vi_full": merged_audio_path if (mode == "dub_audio" and not subtitle_mode) else None,
            "dubbed_video": dubbed_video_path,
            "thumbnails": content_result.get("thumbnails", []),
            "youtube_metadata": content_result.get("metadata_file"),
            "tts_pending_segments": pending_tts_path if os.path.exists(pending_tts_path) else None,
            "tts_segment_dir": tts_cache_dir if os.path.isdir(tts_cache_dir) else None,
        },
    }
    _write_report_and_timing_guide(work_dir, report, segments, tts_results)

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE (Vietnamese)")
    logger.info(f"  Output:    {work_dir}")
    logger.info(f"  Segments:  {report['total_segments']}")
    logger.info(f"  Duration:  {report['total_original_duration']:.1f}s original, "
                f"{report['total_tts_duration']:.1f}s VI audio")
    logger.info(f"  Adjusted:  {report['segments_speed_adjusted']} segments speed-adjusted")
    logger.info(f"  Time:      {elapsed:.1f}s")
    if youtube_url:
        logger.info(f"  YouTube:   {youtube_url}")
    if facebook_url:
        logger.info(f"  Facebook:  {facebook_url}")
    logger.info("=" * 60)

    return report


def main():
    args = parse_args()
    try:
        if args.publish_only:
            from src.publish_existing import publish_existing_session

            result = publish_existing_session(args.resume, args.publish_only)
            if result.get("success"):
                logger.info(
                    "Publish-only complete: platform=%s url=%s",
                    args.publish_only,
                    result.get("url"),
                )
            else:
                logger.error(
                    "Publish-only failed: platform=%s error=%s",
                    args.publish_only,
                    result.get("error"),
                )
                sys.exit(1)
            return

        run_pipeline_vi(
            url=args.url,
            file_path=args.file,
            source_lang=args.source_lang,
            voice_id=args.voice_id,
            skip_video=args.skip_video,
            output_dir=args.output_dir,
            resume_dir=args.resume,
            bg_mode=args.bg_mode,
            bg_duck_db=args.bg_duck_db,
            publish_youtube=args.publish_youtube,
            publish_facebook=args.publish_facebook,
            pause_for_speakers=args.pause_for_speakers,
            burn_subtitles=args.burn_subtitles,
            mode=args.mode,
            cover_original_subtitles=args.cover_original_subtitles,
            subtitle_style=args.subtitle_style,
            subtitle_font_size=args.subtitle_font_size,
            mask_opacity=args.mask_opacity,
            no_dub_audio=args.no_dub_audio,
            from_step=args.from_step,
        )
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
