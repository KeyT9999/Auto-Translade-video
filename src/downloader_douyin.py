"""Douyin downloader — primary strategy: yt-dlp Python module.

Strategy order:
  1. yt-dlp (python -m yt_dlp) — fastest, no browser needed, works great for Douyin
  2. Playwright headless Chromium — fallback when yt-dlp fails
  3. Playwright visible Chromium — last resort

Requires:
  pip install playwright yt-dlp
  playwright install chromium
  ffmpeg on PATH.
"""
import json
import re
import sys
import subprocess
import time
import urllib.parse
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

from src.utils import setup_logging, ensure_dir

logger = setup_logging("downloader_douyin")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_REFERER = "https://www.douyin.com/"

_DASH_VIDEO_RE = re.compile(r"/media-video-")
_DASH_AUDIO_RE = re.compile(r"/media-audio-")
_CDN_HOST_RE = re.compile(r"\.(zjcdn|douyinvod|douyincdn)\.com|\.bytecdntp\.com|v\d+\.muscdn\.com")
_VIDEO_MIME_RE = re.compile(r"mime_type=video_mp4")
_VIDEO_ID_RE = re.compile(r"/video/(\d+)")

# Stealth JS: mask all common automation indicators that Douyin checks
_STEALTH_JS = """
() => {
    // Remove webdriver flag
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    // Fake plugins
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    // Fake languages
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
    // Remove cdc_ automation vars
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
}
"""


def is_douyin_url(url: str) -> bool:
    if not url:
        return False
    host = urllib.parse.urlparse(url.strip()).netloc.lower()
    return host == "douyin.com" or host.endswith(".douyin.com")


def normalize_douyin_url(url: str) -> str:
    """Rewrite any Douyin URL with modal_id= to direct /video/<id> URL."""
    m = re.search(r"modal_id=(\d+)", url)
    if m:
        video_id = m.group(1)
        new_url = f"https://www.douyin.com/video/{video_id}"
        logger.info(f"Normalizing Douyin URL: {url} -> {new_url}")
        return new_url
    return url


def _bitrate_of(url: str) -> int:
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    try:
        return int(qs.get("br", ["0"])[0])
    except (ValueError, TypeError):
        return 0


def _extract_via_playwright(
    url: str,
    wait_seconds: float = 30.0,
    headless: bool = True,
) -> dict:
    """Open the Douyin page in stealth Chromium and intercept CDN video URLs."""
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--no-first-run",
        "--disable-extensions",
        "--lang=zh-CN",
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=launch_args)
        context = browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        # Inject stealth scripts before any page code runs
        context.add_init_script(_STEALTH_JS)

        page = context.new_page()
        captured = {"dash_video": [], "dash_audio": [], "progressive": []}

        def on_request(req):
            u = req.url
            if not _CDN_HOST_RE.search(u):
                return
            if _DASH_VIDEO_RE.search(u):
                if u not in captured["dash_video"]:
                    captured["dash_video"].append(u)
                    logger.debug(f"Captured DASH video: {u[:80]}")
            elif _DASH_AUDIO_RE.search(u):
                if u not in captured["dash_audio"]:
                    captured["dash_audio"].append(u)
                    logger.debug(f"Captured DASH audio: {u[:80]}")
            elif _VIDEO_MIME_RE.search(u):
                if u not in captured["progressive"]:
                    captured["progressive"].append(u)
                    logger.debug(f"Captured progressive: {u[:80]}")

        page.on("request", on_request)

        logger.info(f"Loading Douyin page (headless={headless}): {url}")
        try:
            # Use "commit" — fires as soon as the HTTP response starts; earlier than domcontentloaded
            # This lets us start capturing video requests immediately
            page.goto(url, wait_until="commit", timeout=30000)
            logger.info("Page navigation committed. Waiting for media streams...")
        except Exception as e:
            logger.warning(f"page.goto issue: {type(e).__name__}. Continuing to wait for media streams...")

        # Wait up to wait_seconds for CDN streams to appear
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if captured["progressive"] or (captured["dash_video"] and captured["dash_audio"]):
                logger.info("Media streams captured — stopping early.")
                break
            page.wait_for_timeout(800)

        title = ""
        try:
            title = page.title() or ""
        except Exception:
            pass
        title = re.sub(r"\s*[-–]\s*抖音\s*$", "", title).strip()
        canonical = url  # use normalized URL as canonical

        try:
            canonical = page.url
        except Exception:
            pass

        browser.close()

    logger.info(
        f"Captured: progressive={len(captured['progressive'])} "
        f"dash_video={len(captured['dash_video'])} dash_audio={len(captured['dash_audio'])}"
    )

    m = _VIDEO_ID_RE.search(canonical)
    video_id = m.group(1) if m else ""

    if captured["progressive"]:
        return {
            "mode": "progressive",
            "canonical_url": canonical,
            "video_id": video_id,
            "title": title,
            "video_url": max(captured["progressive"], key=_bitrate_of),
        }

    if captured["dash_video"] and captured["dash_audio"]:
        return {
            "mode": "dash",
            "canonical_url": canonical,
            "video_id": video_id,
            "title": title,
            "video_url": max(captured["dash_video"], key=_bitrate_of),
            "audio_url": max(captured["dash_audio"], key=_bitrate_of),
        }

    return None  # Signal failure without raising


def _extract_via_ytdlp(url: str) -> dict | None:
    """Primary extraction via yt-dlp Python module (python -m yt_dlp).

    yt-dlp's Douyin extractor works reliably without a browser.
    Uses sys.executable so we always use the same Python environment.
    """
    logger.info(f"Extracting via yt-dlp: {url}")
    try:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-warnings",
            "--quiet",
            "--no-check-certificates",
            "--dump-json",
            "--no-playlist",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]/best[ext=mp4]/best",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.warning(f"yt-dlp failed: {result.stderr[:300]}")
            return None

        info = json.loads(result.stdout.strip().splitlines()[-1])

        # Get the direct URL
        video_url = info.get("url") or info.get("webpage_url")
        requested_formats = info.get("requested_formats", [])

        if requested_formats and len(requested_formats) >= 2:
            # Separate video and audio streams
            v_url = requested_formats[0].get("url", "")
            a_url = requested_formats[1].get("url", "")
            if v_url and a_url:
                logger.info(f"yt-dlp extracted DASH streams: video={v_url[:60]}...")
                return {
                    "mode": "dash",
                    "canonical_url": info.get("webpage_url", url),
                    "video_id": str(info.get("id", "")),
                    "title": info.get("title", ""),
                    "video_url": v_url,
                    "audio_url": a_url,
                }
        elif video_url:
            logger.info(f"yt-dlp extracted progressive: {video_url[:60]}...")
            return {
                "mode": "progressive",
                "canonical_url": info.get("webpage_url", url),
                "video_id": str(info.get("id", "")),
                "title": info.get("title", ""),
                "video_url": video_url,
            }
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timed out.")
    except Exception as e:
        logger.warning(f"yt-dlp extraction error: {e}")

    return None


def _download_stream(url: str, dest: Path) -> int:
    headers = {
        "User-Agent": _UA,
        "Referer": _REFERER,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    size = 0
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    size += len(chunk)
    return size


def _ffmpeg_mux(video_path: Path, audio_path: Path, output_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c", "copy",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed: {proc.stderr[-500:]}")


def _ffprobe_duration(path: Path) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nokey=1:noprint_wrappers=1",
                str(path),
            ],
            text=True,
        )
        return float(out.strip())
    except Exception:
        return 0.0


def _download_info(info: dict, out_dir: Path, video_id: str, final_path: Path) -> None:
    """Download video from an extracted info dict (either progressive or dash)."""
    if info["mode"] == "progressive":
        logger.info(f"Downloading progressive MP4 id={video_id}")
        size = _download_stream(info["video_url"], final_path)
        logger.info(f"Stream downloaded: {size:,}B")
    else:
        tmp_video = out_dir / f"_tmp_{video_id}.video.mp4"
        tmp_audio = out_dir / f"_tmp_{video_id}.audio.m4a"
        try:
            logger.info(f"Downloading DASH video stream id={video_id}")
            v_size = _download_stream(info["video_url"], tmp_video)
            logger.info(f"Downloading DASH audio stream id={video_id}")
            a_size = _download_stream(info["audio_url"], tmp_audio)
            logger.info(f"Streams downloaded: video={v_size:,}B audio={a_size:,}B")
            _ffmpeg_mux(tmp_video, tmp_audio, final_path)
        finally:
            for p in (tmp_video, tmp_audio):
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass


def download_douyin(
    url: str,
    output_dir: str,
    filename: str | None = None,
) -> dict:
    """Download a Douyin video and return metadata matching download_one() shape.

    Strategy:
      1. Playwright (headless stealth Chromium) — intercept CDN requests
      2. Playwright (visible window) — if headless blocked
      3. yt-dlp — final fallback

    Returned dict keys:
        input_url, canonical_url, platform, video_id, title, uploader,
        duration, filepath
    """
    if not url:
        raise ValueError("URL cannot be empty")

    url = normalize_douyin_url(url)
    ensure_dir(output_dir)
    out_dir = Path(output_dir)

    # --- Strategy 1: yt-dlp (fastest, no browser needed) ---
    info = _extract_via_ytdlp(url)

    # --- Strategy 2: Headless Playwright (if yt-dlp fails) ---
    if not info:
        logger.warning("yt-dlp failed. Trying headless Playwright...")
        info = _extract_via_playwright(url, wait_seconds=30.0, headless=True)

    # --- Strategy 3: Visible Playwright (last resort) ---
    if not info:
        logger.warning("Headless Playwright also failed. Trying visible browser...")
        info = _extract_via_playwright(url, wait_seconds=35.0, headless=False)

    if not info:
        raise RuntimeError(
            f"All download strategies failed for: {url}\n"
            "Possible causes:\n"
            "  - Network cannot reach douyin.com (blocked in your region)\n"
            "  - VPN or proxy is needed\n"
            "  - Video is private or geo-restricted\n"
            "Try opening the URL manually in a browser first."
        )

    video_id = info.get("video_id") or "unknown"
    name = filename or f"Douyin_{video_id}.mp4"
    final_path = out_dir / name

    _download_info(info, out_dir, video_id, final_path)

    duration = _ffprobe_duration(final_path)
    logger.info(f"Saved: {final_path} ({duration:.1f}s)")

    return {
        "input_url": url,
        "canonical_url": info.get("canonical_url", url),
        "platform": "Douyin",
        "video_id": video_id,
        "title": info.get("title", ""),
        "uploader": "",
        "duration": duration,
        "filepath": str(final_path),
    }
