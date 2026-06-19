"""Vietnamese TTS Synthesizer using LucyLab API.

Flow:
    1. POST ttsLongText → get projectExportId
    2. Poll getExportStatus until state == "completed"
    3. Download audio from returned URL
"""
import os
import time
import requests
from pydub import AudioSegment
import config
from src.utils import setup_logging

logger = setup_logging("synthesizer_vi")

POLL_INTERVAL = 2  # seconds between status checks
POLL_TIMEOUT = int(os.getenv("LUCYLAB_POLL_TIMEOUT", "300"))  # max seconds to wait for TTS completion


def _call_lucylab(method: str, input_data: dict) -> dict:
    """Call LucyLab JSON-RPC API."""
    response = requests.post(
        config.LUCYLAB_API_URL,
        headers={
            "Authorization": f"Bearer {config.VIETNAMESE_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "method": method,
            "input": input_data,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"LucyLab API error: {data['error']}")

    return data.get("result", {})


def _wait_for_audio(export_id: str) -> str:
    """Poll getExportStatus until completed, return audio URL."""
    start = time.time()

    while time.time() - start < POLL_TIMEOUT:
        result = _call_lucylab("getExportStatus", {"projectExportId": export_id})
        state = result.get("state", "")

        if state == "completed":
            url = result.get("url", "")
            if not url:
                raise RuntimeError("TTS completed but no audio URL returned")
            return url

        if state == "failed":
            raise RuntimeError(f"TTS job failed: {result}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"TTS polling timed out after {POLL_TIMEOUT}s for export {export_id}")


def _download_audio(url: str, output_path: str) -> str:
    """Download audio file from URL."""
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)

    return output_path


def _call_larvoice(text_vi: str, voice_id: str, speed: float) -> str:
    """Call LarVoice TTS API and return the audio URL, polling if necessary."""
    if not config.VIETNAMESE_API_KEY:
        raise ValueError("LARVOICE_API_KEY is not set (mapped as VIETNAMESE_API_KEY). Check your .env file.")

    headers = {
        "Authorization": f"Bearer {config.VIETNAMESE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "language": "vi",
        "post_speed": speed,
        "post_volume": 0,
        "post_pitch": 0,
        "sentence_pause_ms": 750,
        "line_break_pause_ms": 800,
        "ellipsis_pause_ms": 800,
        "comma_pause_ms": 220,
        "gen_text": text_vi,
        "voice_id": voice_id
    }

    # Make the POST request to LarVoice API
    api_url = getattr(config, "LARVOICE_API_URL", "https://larvoice.com/api/v1/tts")
    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()

    if "error" in result:
        raise RuntimeError(f"LarVoice API returned error: {result['error']}")

    data = result.get("data", {})
    status = data.get("status")
    job_id = data.get("job_id")

    if status == "completed":
        audio_url = data.get("audio_url") or data.get("output_url")
        if not audio_url:
            raise RuntimeError("LarVoice TTS completed but no audio URL was returned.")
        return audio_url

    # Fallback to polling
    base_jobs_url = api_url.replace("/tts", "/jobs")
    poll_url = f"{base_jobs_url}/{job_id}"
    logger.info(f"LarVoice TTS status: {status}. Polling job {job_id}...")

    start_time = time.time()
    while time.time() - start_time < POLL_TIMEOUT:
        poll_response = requests.get(poll_url, headers={"Authorization": f"Bearer {config.VIETNAMESE_API_KEY}"}, timeout=15)
        poll_response.raise_for_status()
        
        job_result = poll_response.json()
        job_data = job_result.get("data", {}).get("job", {})
        
        current_status = job_data.get("status")
        if current_status == "completed":
            audio_url = job_data.get("audio_url") or job_data.get("output_url")
            if not audio_url:
                raise RuntimeError("LarVoice TTS completed but no audio URL was returned in job details.")
            return audio_url
        elif current_status == "failed":
            error_msg = job_data.get("error", "Unknown LarVoice error")
            raise RuntimeError(f"LarVoice TTS job failed: {error_msg}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"LarVoice TTS polling timed out after {POLL_TIMEOUT}s for job {job_id}")


def synthesize_segment_vi(
    text_vi: str,
    output_path: str,
    target_duration: float | None = None,
    voice_id: str | None = None,
) -> dict:
    """Synthesize Vietnamese text to audio using LucyLab or LarVoice API.

    Args:
        text_vi: Vietnamese text to speak
        output_path: Where to save the WAV file
        target_duration: Target duration in seconds (for speed adjustment)
        voice_id: TTS voice ID (default from config)

    Returns:
        dict with path, actual_duration, speed_adjusted, rate_applied
    """
    if not voice_id:
        raise ValueError("voice_id is required. Use --voice male/female or set VIETNAMESE_VOICEID_MALE/FEMALE in .env")
    if not config.VIETNAMESE_API_KEY:
        raise ValueError("VIETNAMESE_API_KEY / LARVOICE_API_KEY not set in .env")

    max_speed = config.VIETNAMESE_TTS_MAX_SPEED
    provider = getattr(config, "TTS_PROVIDER", "lucylab")

    # --- Step 1: Estimate optimal speed based on text length and target duration ---
    # Calibrated from LucyLab male voice: ~19 chars/sec at 1.0x (measured by
    # running 114 chars through TTS at 1.3x → 4.6s output → 19.1 chars/sec at 1.0x).
    # Add a 10% safety headroom so we tolerate slight tail silence without
    # speeding up the audio unnecessarily.
    chars_per_sec_normal = 19.0
    safety_headroom = 1.10
    estimated_normal_duration = len(text_vi) / chars_per_sec_normal

    speed = 1.0
    if target_duration and estimated_normal_duration > 0:
        # Only speed up if the natural-paced VI would overflow the target by
        # more than the safety headroom.
        estimated_ratio = estimated_normal_duration / (target_duration * safety_headroom)
        if estimated_ratio > 1.0:
            speed = min(estimated_ratio, max_speed)
            speed = round(speed, 2)

    # --- Step 2: Call TTS API ---
    logger.info(f"TTS request ({provider}): {len(text_vi)} chars, speed={speed}, target={target_duration:.1f}s"
                if target_duration else f"TTS request ({provider}): {len(text_vi)} chars, speed={speed}")

    if provider == "larvoice":
        audio_url = _call_larvoice(text_vi, voice_id, speed)
        speed_adjusted = speed != 1.0
    else:
        # LucyLab flow
        result = _call_lucylab("ttsLongText", {
            "text": text_vi,
            "userVoiceId": voice_id,
            "speed": speed,
        })

        export_id = result.get("projectExportId")
        if not export_id:
            raise RuntimeError(f"No projectExportId in response: {result}")

        logger.info(f"TTS job created: {export_id} (chars={result.get('characterCount', '?')}, "
                    f"blocks={result.get('blockCount', '?')})")

        audio_url = _wait_for_audio(export_id)
        speed_adjusted = speed != 1.0

    logger.info(f"TTS completed, downloading audio...")

    # Download to a temp file first (API may return mp3 or wav)
    temp_path = output_path + ".tmp"
    _download_audio(audio_url, temp_path)

    # Convert to WAV for consistency with the rest of the pipeline
    audio = AudioSegment.from_file(temp_path)
    audio.export(output_path, format="wav")
    os.remove(temp_path)

    actual_duration = len(audio) / 1000.0

    # --- Step 4: If still too long, we can't re-synthesize easily (API cost),
    # just log a warning or try one more time if speed < max_speed ---
    if target_duration and actual_duration > target_duration * 1.1:
        if speed < max_speed:
            # Try once more with higher speed
            new_speed = min(actual_duration / target_duration * speed, max_speed)
            new_speed = round(new_speed, 2)
            logger.info(
                f"Re-adjusting speed: {actual_duration:.1f}s → ~{target_duration:.1f}s "
                f"(speed: {speed} → {new_speed})"
            )

            if provider == "larvoice":
                audio_url2 = _call_larvoice(text_vi, voice_id, new_speed)
            else:
                result2 = _call_lucylab("ttsLongText", {
                    "text": text_vi,
                    "userVoiceId": voice_id,
                    "speed": new_speed,
                })
                export_id2 = result2.get("projectExportId")
                audio_url2 = _wait_for_audio(export_id2) if export_id2 else None

            if audio_url2:
                _download_audio(audio_url2, temp_path)
                audio = AudioSegment.from_file(temp_path)
                audio.export(output_path, format="wav")
                os.remove(temp_path)
                actual_duration = len(audio) / 1000.0
                speed = new_speed
                speed_adjusted = True
        else:
            logger.warning(
                f"Segment too long ({actual_duration:.1f}s vs {target_duration:.1f}s target). "
                f"Already at max speed {max_speed}x — adjust in CapCut."
            )

    return {
        "path": output_path,
        "actual_duration": round(actual_duration, 3),
        "speed_adjusted": speed_adjusted,
        "rate_applied": f"{speed}x",
    }

