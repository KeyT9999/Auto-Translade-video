import argparse
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
from pipeline_vi import _get_default_vi_output_dir
from src.batch_runner import BatchRunner, create_batch_state, load_batch_state


def _flatten_platform_args(values):
    platforms = []
    for group in values or []:
        for platform in group:
            normalized = platform.strip().lower()
            if normalized and normalized not in platforms:
                platforms.append(normalized)
    return platforms


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sequential batch queue runner for the Vietnamese video pipeline."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--input", help="Text file containing 1-50 links, one per line.")
    source_group.add_argument("--resume", help="Existing batch directory to resume.")

    parser.add_argument(
        "--mode",
        choices=["dub_audio", "subtitle_only"],
        default="subtitle_only",
        help="Output mode for each job (default: subtitle_only).",
    )
    parser.add_argument(
        "--source-lang",
        default=config.DEFAULT_SOURCE_LANG,
        help=f"Source language for all videos (default: {config.DEFAULT_SOURCE_LANG}).",
    )
    parser.add_argument(
        "--output-dir",
        default=_get_default_vi_output_dir(),
        help="Session output root for single-video pipeline runs.",
    )
    parser.add_argument(
        "--publish",
        action="append",
        nargs="+",
        choices=["youtube", "facebook"],
        help="Publish rendered videos to one or more platforms.",
    )
    parser.add_argument(
        "--retry-publish",
        action="append",
        nargs="+",
        choices=["youtube", "facebook"],
        help="Retry publish only, reusing the existing rendered session output.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="When resuming a batch, rerun jobs with status=failed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate links and create queue files without processing videos.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop the batch immediately after a failed or publish_failed job.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing later jobs after a failed job.",
    )
    parser.add_argument(
        "--delay-between-videos",
        type=int,
        default=None,
        help="Override delay between jobs in seconds.",
    )
    parser.add_argument("--voice", choices=["male", "female"], default=None)
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument("--bg-mode", choices=["demucs", "duck", "none"], default="demucs")
    parser.add_argument("--bg-duck-db", type=float, default=-12.0)
    parser.add_argument("--burn-subtitles", action="store_true")
    parser.add_argument("--cover-original-subtitles", action="store_true")
    parser.add_argument("--subtitle-style", choices=["boxed", "plain"], default="plain")
    parser.add_argument("--subtitle-font-size", type=int, default=None)
    parser.add_argument("--mask-opacity", type=float, default=None)
    parser.add_argument("--no-dub-audio", action="store_true")
    parser.add_argument("--logo-path", default=None, help="Path to logo image file.")
    parser.add_argument(
        "--logo-position",
        choices=["top_left", "top_right", "bottom_left", "bottom_right"],
        default="top_right",
        help="Position to overlay logo.",
    )
    parser.add_argument("--logo-width", type=int, default=None, help="Scale logo to width in pixels.")
    parser.add_argument(
        "--output-speed",
        type=float,
        default=config.OUTPUT_PLAYBACK_SPEED,
        help=f"Output video playback speed: 1.0, 1.1, 1.2, 1.3 (default: {config.OUTPUT_PLAYBACK_SPEED})",
    )
    args = parser.parse_args()
    from src.output_speed import validate_output_speed
    try:
        args.output_speed = validate_output_speed(args.output_speed)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def main() -> None:
    args = parse_args()
    from src.ai import ai_router
    ai_router.reset_failures()
    publish_platforms = _flatten_platform_args(args.publish)
    retry_publish_platforms = _flatten_platform_args(args.retry_publish)

    if args.retry_failed and not args.resume:
        raise SystemExit("--retry-failed requires --resume")
    if retry_publish_platforms and not args.resume:
        raise SystemExit("--retry-publish requires --resume")
    if args.dry_run and args.resume:
        raise SystemExit("--dry-run can only be used with --input")

    runner = BatchRunner()

    if args.input:
        extra_options = {
            "voice": args.voice,
            "skip_video": args.skip_video,
            "bg_mode": args.bg_mode,
            "bg_duck_db": args.bg_duck_db,
            "burn_subtitles": args.burn_subtitles,
            "cover_original_subtitles": args.cover_original_subtitles,
            "subtitle_style": args.subtitle_style,
            "subtitle_font_size": args.subtitle_font_size,
            "mask_opacity": args.mask_opacity,
            "no_dub_audio": args.no_dub_audio,
            "logo_path": args.logo_path,
            "logo_position": args.logo_position,
            "logo_width": args.logo_width,
            "output_playback_speed": args.output_speed,
        }
        batch = create_batch_state(
            args.input,
            mode=args.mode,
            source_lang=args.source_lang,
            output_root=args.output_dir,
            publish_platforms=publish_platforms,
            extra_options=extra_options,
            dry_run=args.dry_run,
            stop_on_error=args.stop_on_error or None,
            continue_on_error=args.continue_on_error or None,
            delay_between_videos_seconds=args.delay_between_videos,
        )
    else:
        batch = load_batch_state(args.resume)
        if args.stop_on_error:
            batch.stop_on_error = True
            batch.continue_on_error = False
        elif args.continue_on_error:
            batch.stop_on_error = False
            batch.continue_on_error = True
        if args.delay_between_videos is not None:
            batch.delay_between_videos_seconds = max(0, args.delay_between_videos)

    batch = runner.run(
        batch,
        retry_failed=args.retry_failed,
        retry_publish_platforms=retry_publish_platforms,
    )
    print(os.path.abspath(batch.batch_dir))


if __name__ == "__main__":
    main()
