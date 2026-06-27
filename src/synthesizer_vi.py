"""Vietnamese TTS Synthesizer using LucyLab or LarVoice APIs."""

from __future__ import annotations

import os
import subprocess
import time

import requests
from pydub import AudioSegment

import config
from src.utils import setup_logging

logger = setup_logging("synthesizer_vi")

import sys
import atexit

_local_server_process = None
_server_started_by_us = False

def _ensure_local_omnivoice_server_running() -> str:
    """Checks if the local sidecar server is running, and starts it if not."""
    global _local_server_process, _server_started_by_us
    port = getattr(config, "OMNIVOICE_LOCAL_PORT", 3901)
    base_url = f"http://127.0.0.1:{port}"
    
    # Check if already running
    try:
        response = requests.get(f"{base_url}/ping", timeout=1)
        if response.status_code == 200:
            status = response.json().get("status")
            if status == "ready":
                logger.info("Local OmniVoice sidecar server is already running and ready.")
                return base_url
    except requests.RequestException:
        pass
        
    # If not running, start it
    logger.info("Local OmniVoice sidecar server is not running. Starting it...")
    studio_path = getattr(config, "OMNIVOICE_STUDIO_PATH", "d:/MMO/OmniVoice-Studio")
    venv_python = os.path.join(studio_path, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        venv_python = "python"
        
    server_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "omnivoice_local_server.py")
    if not os.path.exists(server_script):
        server_script = "tools/omnivoice_local_server.py"
        
    cmd = [venv_python, server_script, "--port", str(port)]
    logger.info("Running command: %s", " ".join(cmd))
    
    _local_server_process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True
    )
    _server_started_by_us = True
    
    # Wait for the server to be ready
    start_time = time.time()
    timeout = 25.0
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{base_url}/ping", timeout=1)
            if response.status_code == 200:
                status = response.json().get("status")
                if status == "ready":
                    logger.info("Local OmniVoice sidecar server started and ready in %.1fs.", time.time() - start_time)
                    return base_url
                else:
                    logger.info("Local OmniVoice sidecar server is loading model... (status: %s)", status)
        except requests.RequestException:
            pass
        time.sleep(1.0)
        
    raise RuntimeError(f"Timed out waiting for local OmniVoice server to start on port {port} (timeout={timeout}s)")

def _shutdown_local_omnivoice_server():
    """Sends a shutdown command to the local server if we started it."""
    global _local_server_process, _server_started_by_us
    if not _server_started_by_us:
        return
    port = getattr(config, "OMNIVOICE_LOCAL_PORT", 3901)
    base_url = f"http://127.0.0.1:{port}"
    logger.info("Shutting down local OmniVoice sidecar server on port %s...", port)
    try:
        requests.post(f"{base_url}/shutdown", timeout=2)
    except requests.RequestException:
        pass
    if _local_server_process:
        try:
            _local_server_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _local_server_process.kill()
        _local_server_process = None
        _server_started_by_us = False
        logger.info("Local OmniVoice sidecar server process terminated.")

# Register the cleanup hook
atexit.register(_shutdown_local_omnivoice_server)

POLL_INTERVAL = 2
POLL_TIMEOUT = int(os.getenv("LUCYLAB_POLL_TIMEOUT", "300"))
LUCYLAB_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
LUCYLAB_DOWNLOAD_BACKOFFS = [2, 4, 8, 15, 30, 45, 60, 90]


class TTSSegmentError(RuntimeError):
    """Structured segment-level TTS failure."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        job_id: str | None = None,
        audio_url: str | None = None,
        status_code: int | None = None,
        attempts: int = 0,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.job_id = job_id
        self.audio_url = audio_url
        self.status_code = status_code
        self.attempts = attempts


def _call_lucylab(method: str, input_data: dict) -> dict:
    response = requests.post(
        config.LUCYLAB_API_URL,
        headers={
            "Authorization": f"Bearer {config.VIETNAMESE_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"method": method, "input": input_data},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"LucyLab API error: {data['error']}")

    return data.get("result", {})


def _get_lucylab_export_status(export_id: str) -> dict:
    return _call_lucylab("getExportStatus", {"projectExportId": export_id})


def _wait_for_audio(export_id: str) -> str:
    start = time.time()

    while time.time() - start < POLL_TIMEOUT:
        result = _get_lucylab_export_status(export_id)
        state = str(result.get("state", "")).lower().strip()

        if state == "completed":
            url = result.get("url", "")
            if not url:
                raise RuntimeError("TTS completed but no audio URL returned")
            return url

        if state == "failed":
            raise RuntimeError(f"TTS job failed: {result}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"TTS polling timed out after {POLL_TIMEOUT}s for export {export_id}")


def is_valid_audio_file(path: str) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) <= 0:
        return False

    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            return False
    except Exception:
        return False

    try:
        audio = AudioSegment.from_file(path)
        return len(audio) > 0
    except Exception:
        return False


def _refresh_audio_url_if_needed(
    url: str,
    provider: str,
    export_id: str | None = None,
) -> str:
    if provider != "lucylab" or not export_id:
        return url

    try:
        result = _get_lucylab_export_status(export_id)
        state = str(result.get("state", "")).lower().strip()
        if state == "failed":
            raise RuntimeError(f"TTS job failed while retrying download: {result}")
        refreshed_url = str(result.get("url") or "").strip()
        return refreshed_url or url
    except Exception as exc:
        logger.warning("LucyLab status refresh failed for %s: %s", export_id, exc)
        return url


def _download_audio(
    url: str,
    output_path: str,
    *,
    provider: str = "lucylab",
    export_id: str | None = None,
) -> dict:
    backoffs = LUCYLAB_DOWNLOAD_BACKOFFS if provider == "lucylab" else [0]
    current_url = url
    last_error: str | None = None
    last_status_code: int | None = None
    download_tmp = output_path + ".part"

    for attempt, backoff in enumerate(backoffs, start=1):
        if attempt > 1:
            current_url = _refresh_audio_url_if_needed(current_url, provider, export_id=export_id)

        try:
            response = requests.get(current_url, timeout=60, stream=True)
            status_code = response.status_code
            last_status_code = status_code

            content_length = response.headers.get("Content-Length")
            if status_code != 200:
                error_message = f"HTTP {status_code} when downloading audio"
                if provider == "lucylab" and status_code in LUCYLAB_RETRYABLE_STATUS_CODES:
                    last_error = error_message
                else:
                    response.raise_for_status()
            elif content_length is not None and int(content_length or "0") <= 0:
                last_error = "Downloaded audio response had zero Content-Length"
            else:
                with open(download_tmp, "wb") as handle:
                    wrote_bytes = 0
                    for chunk in response.iter_content(chunk_size=1024 * 64):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        wrote_bytes += len(chunk)

                if wrote_bytes <= 0:
                    last_error = "Downloaded audio response was empty"
                else:
                    os.replace(download_tmp, output_path)
                    if is_valid_audio_file(output_path):
                        return {
                            "path": output_path,
                            "audio_url": current_url,
                            "attempts": attempt,
                            "retry_count": attempt - 1,
                            "status_code": status_code,
                        }
                    last_error = "Downloaded file is not a valid audio payload"
                    if os.path.exists(output_path):
                        os.remove(output_path)

        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            status_code = response.status_code if response is not None else None
            last_status_code = status_code
            if provider == "lucylab" and status_code in LUCYLAB_RETRYABLE_STATUS_CODES:
                last_error = f"{status_code} {response.reason if response is not None else 'HTTP error'}"
            else:
                raise TTSSegmentError(
                    str(exc),
                    provider=provider,
                    job_id=export_id,
                    audio_url=current_url,
                    status_code=status_code,
                    attempts=attempt,
                ) from exc
        except requests.RequestException as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)
        finally:
            if os.path.exists(download_tmp):
                os.remove(download_tmp)

        if attempt < len(backoffs):
            logger.warning(
                "Audio download attempt %s/%s failed for %s: %s. Retrying in %ss...",
                attempt,
                len(backoffs),
                provider,
                last_error,
                backoff,
            )
            time.sleep(backoff)

    raise TTSSegmentError(
        last_error or "Audio download failed after retries",
        provider=provider,
        job_id=export_id,
        audio_url=current_url,
        status_code=last_status_code,
        attempts=len(backoffs),
    )


def _call_larvoice(text_vi: str, voice_id: str, speed: float) -> tuple[str, str | None]:
    if not config.VIETNAMESE_API_KEY:
        raise ValueError("LARVOICE_API_KEY is not set (mapped as VIETNAMESE_API_KEY). Check your .env file.")

    headers = {
        "Authorization": f"Bearer {config.VIETNAMESE_API_KEY}",
        "Content-Type": "application/json",
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
        "voice_id": voice_id,
    }

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
        return audio_url, job_id

    base_jobs_url = api_url.replace("/tts", "/jobs")
    poll_url = f"{base_jobs_url}/{job_id}"
    logger.info("LarVoice TTS status: %s. Polling job %s...", status, job_id)

    start_time = time.time()
    while time.time() - start_time < POLL_TIMEOUT:
        poll_response = requests.get(
            poll_url,
            headers={"Authorization": f"Bearer {config.VIETNAMESE_API_KEY}"},
            timeout=15,
        )
        poll_response.raise_for_status()

        job_result = poll_response.json()
        job_data = job_result.get("data", {}).get("job", {})

        current_status = job_data.get("status")
        if current_status == "completed":
            audio_url = job_data.get("audio_url") or job_data.get("output_url")
            if not audio_url:
                raise RuntimeError("LarVoice TTS completed but no audio URL was returned in job details.")
            return audio_url, job_id
        if current_status == "failed":
            error_msg = job_data.get("error", "Unknown LarVoice error")
            raise RuntimeError(f"LarVoice TTS job failed: {error_msg}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"LarVoice TTS polling timed out after {POLL_TIMEOUT}s for job {job_id}")


def _render_downloaded_audio_to_wav(
    source_path: str,
    output_path: str,
) -> tuple[AudioSegment, float]:
    temp_wav_path = output_path + ".tmp.wav"
    audio = AudioSegment.from_file(source_path)
    audio.export(temp_wav_path, format="wav")

    if not is_valid_audio_file(temp_wav_path):
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)
        raise RuntimeError("Rendered WAV failed audio validation")

    os.replace(temp_wav_path, output_path)
    return audio, len(audio) / 1000.0


def _call_tiktok(text_vi: str, voice_id: str) -> bytes:
    import base64
    
    url = "https://api16-normal-c-useast1a.tiktokv.com/media/api/text/speech/invoke/"
    headers = {
        "User-Agent": "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 7.1.2; es_US; SM-G965N; Build/QP1A.190711.020; Cronet/TTNetVersion:5f964076 2021-12-10 QuicVersion:477b2526 2021-11-23)",
    }
    
    session_id = getattr(config, "TIKTOK_SESSION_ID", "")
    if session_id:
        headers["Cookie"] = f"sessionid={session_id}"
        
    params = {
        "req_text": text_vi,
        "speaker_map_type": 0,
        "text_speaker": voice_id,
        "aid": 1233
    }
    
    response = requests.post(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    result = response.json()
    
    status_code = result.get("status_code")
    if status_code != 0:
        message = result.get("message", "Unknown TikTok TTS error")
        raise RuntimeError(f"TikTok TTS API returned error (status_code {status_code}): {message}")
        
    data = result.get("data", {})
    v_str = data.get("v_str")
    if not v_str:
        raise RuntimeError("TikTok TTS response did not contain 'v_str' field.")
        
    return base64.b64decode(v_str)


def synthesize_segment_vi(
    text_vi: str,
    output_path: str,
    target_duration: float | None = None,
    voice_id: str | None = None,
) -> dict:
    provider = getattr(config, "TTS_PROVIDER", "lucylab")
    
    # Auto-detect if voice_id is an OmniVoice ID, local audio file, or TikTok voice
    if voice_id:
        is_omnivoice_hex = len(voice_id) == 8 and all(c in "0123456789abcdefABCDEF" for c in voice_id)
        is_local_file = voice_id.lower().endswith((".wav", ".mp3"))
        if is_omnivoice_hex or is_local_file:
            provider = "omnivoice"
        elif voice_id.startswith("vi_vn_") or voice_id.startswith("BV07"):
            provider = "tiktok"
            if voice_id == "vi_vn_001":
                voice_id = "BV075_streaming"
            elif voice_id == "vi_vn_002":
                voice_id = "BV074_streaming"

    if not voice_id and provider != "omnivoice":
        raise ValueError("voice_id is required. Use --voice male/female or set VIETNAMESE_VOICEID_MALE/FEMALE in .env")
    if provider != "omnivoice" and not config.VIETNAMESE_API_KEY:
        raise ValueError("VIETNAMESE_API_KEY / LARVOICE_API_KEY not set in .env")

    max_speed = config.VIETNAMESE_TTS_MAX_SPEED
    raw_download_path = output_path + ".download"

    chars_per_sec_normal = 19.0
    safety_headroom = 1.10
    estimated_normal_duration = len(text_vi) / chars_per_sec_normal

    speed = 1.0
    if target_duration and estimated_normal_duration > 0:
        estimated_ratio = estimated_normal_duration / (target_duration * safety_headroom)
        if estimated_ratio > 1.0:
            speed = round(min(estimated_ratio, max_speed), 2)

    logger.info(
        f"TTS request ({provider}): {len(text_vi)} chars, speed={speed}, target={target_duration:.1f}s"
        if target_duration
        else f"TTS request ({provider}): {len(text_vi)} chars, speed={speed}"
    )

    if provider == "omnivoice":
        try:
            base_url = _ensure_local_omnivoice_server_running()
            payload = {
                "text": text_vi,
                "voice_id": voice_id,
                "speed": speed,
                "target_duration": target_duration
            }
            response = requests.post(f"{base_url}/synthesize", json=payload, timeout=90)
            if response.status_code != 200:
                raise RuntimeError(f"Server returned status code {response.status_code}: {response.text}")
                
            with open(output_path, "wb") as f:
                f.write(response.content)
                
            if not is_valid_audio_file(output_path):
                raise RuntimeError("Generated file is not a valid audio payload")
                
            audio = AudioSegment.from_file(output_path)
            actual_duration = len(audio) / 1000.0
            
            return {
                "path": output_path,
                "actual_duration": round(actual_duration, 3),
                "speed_adjusted": speed != 1.0,
                "rate_applied": f"{speed}x",
                "provider": "omnivoice",
                "voice_id": voice_id,
                "job_id": "local",
                "audio_url": "local",
                "retry_count": 0,
                "status": "generated",
            }
        except Exception as exc:
            raise TTSSegmentError(
                f"Local OmniVoice synthesis failed: {exc}",
                provider="omnivoice",
                job_id="local",
            ) from exc

    if provider == "tiktok":
        try:
            audio_bytes = _call_tiktok(text_vi, voice_id)
            with open(raw_download_path, "wb") as f:
                f.write(audio_bytes)
                
            audio, actual_duration = _render_downloaded_audio_to_wav(raw_download_path, output_path)
            if os.path.exists(raw_download_path):
                os.remove(raw_download_path)
                
            return {
                "path": output_path,
                "actual_duration": round(actual_duration, 3),
                "speed_adjusted": False,
                "rate_applied": "1.0x",
                "provider": "tiktok",
                "voice_id": voice_id,
                "job_id": "tiktok",
                "audio_url": "tiktok",
                "retry_count": 0,
                "status": "generated",
            }
        except Exception as exc:
            if os.path.exists(raw_download_path):
                try:
                    os.remove(raw_download_path)
                except OSError:
                    pass
            raise TTSSegmentError(
                f"TikTok TTS synthesis failed: {exc}",
                provider="tiktok",
                job_id="tiktok",
            ) from exc

    job_id: str | None = None
    audio_url: str | None = None
    total_retry_count = 0

    try:
        if provider == "larvoice":
            audio_url, job_id = _call_larvoice(text_vi, voice_id, speed)
            speed_adjusted = speed != 1.0
        else:
            result = _call_lucylab(
                "ttsLongText",
                {"text": text_vi, "userVoiceId": voice_id, "speed": speed},
            )

            export_id = result.get("projectExportId")
            if not export_id:
                raise RuntimeError(f"No projectExportId in response: {result}")
            job_id = export_id

            logger.info(
                "TTS job created: %s (chars=%s, blocks=%s)",
                export_id,
                result.get("characterCount", "?"),
                result.get("blockCount", "?"),
            )

            audio_url = _wait_for_audio(export_id)
            speed_adjusted = speed != 1.0

        logger.info("TTS completed, downloading audio...")
        download_meta = _download_audio(audio_url, raw_download_path, provider=provider, export_id=job_id)
        total_retry_count += int(download_meta.get("retry_count", 0))

        audio, actual_duration = _render_downloaded_audio_to_wav(raw_download_path, output_path)
        if os.path.exists(raw_download_path):
            os.remove(raw_download_path)

        if target_duration and actual_duration > target_duration * 1.1:
            if speed < max_speed:
                new_speed = round(min(actual_duration / target_duration * speed, max_speed), 2)
                logger.info(
                    "Re-adjusting speed: %.1fs -> ~%.1fs (speed: %s -> %s)",
                    actual_duration,
                    target_duration,
                    speed,
                    new_speed,
                )

                if provider == "larvoice":
                    audio_url, job_id = _call_larvoice(text_vi, voice_id, new_speed)
                else:
                    result2 = _call_lucylab(
                        "ttsLongText",
                        {"text": text_vi, "userVoiceId": voice_id, "speed": new_speed},
                    )
                    export_id2 = result2.get("projectExportId")
                    if not export_id2:
                        raise RuntimeError(f"No projectExportId in response: {result2}")
                    job_id = export_id2
                    audio_url = _wait_for_audio(export_id2)

                if audio_url:
                    download_meta = _download_audio(
                        audio_url,
                        raw_download_path,
                        provider=provider,
                        export_id=job_id,
                    )
                    total_retry_count += int(download_meta.get("retry_count", 0))
                    audio, actual_duration = _render_downloaded_audio_to_wav(raw_download_path, output_path)
                    if os.path.exists(raw_download_path):
                        os.remove(raw_download_path)
                    speed = new_speed
                    speed_adjusted = True
            else:
                logger.warning(
                    "Segment too long (%.1fs vs %.1fs target). Already at max speed %.1fx.",
                    actual_duration,
                    target_duration,
                    max_speed,
                )

        return {
            "path": output_path,
            "actual_duration": round(actual_duration, 3),
            "speed_adjusted": speed_adjusted,
            "rate_applied": f"{speed}x",
            "provider": provider,
            "voice_id": voice_id,
            "job_id": job_id,
            "audio_url": audio_url,
            "retry_count": total_retry_count,
            "status": "generated",
        }

    except TTSSegmentError:
        raise
    except Exception as exc:
        raise TTSSegmentError(
            str(exc),
            provider=provider,
            job_id=job_id,
            audio_url=audio_url,
        ) from exc
    finally:
        for leftover in (raw_download_path, raw_download_path + ".part", output_path + ".tmp.wav"):
            if os.path.exists(leftover):
                try:
                    os.remove(leftover)
                except OSError:
                    pass
