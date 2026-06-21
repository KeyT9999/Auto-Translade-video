import json
import time
import azure.cognitiveservices.speech as speechsdk
import config
from src.utils import setup_logging

logger = setup_logging("transcriber")


def transcribe_groq(audio_path: str, language: str) -> list[dict] | None:
    if not config.GROQ_API_KEY:
        logger.info("GROQ_API_KEY not set. Skipping Groq ASR.")
        return None

    import subprocess
    import os
    import requests

    temp_mp3 = audio_path + ".mp3"
    try:
        logger.info(f"Compressing WAV to MP3 for Groq upload: {audio_path}")
        # Convert WAV to MP3 at 64k to reduce size and stay below 25MB limit
        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-vn", "-ar", "16000", "-ac", "1", "-ab", "64k",
            temp_mp3
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Failed to compress audio: {result.stderr}")
            return None

        headers = {
            "Authorization": f"Bearer {config.GROQ_API_KEY}"
        }

        # Determine 2-letter language code (e.g. en-US -> en)
        lang_iso = language.split("-")[0] if language else None

        data = {
            "model": "whisper-large-v3",
            "response_format": "verbose_json"
        }
        if lang_iso and lang_iso.lower() != "auto":
            data["language"] = lang_iso

        logger.info(f"Uploading to Groq ASR using whisper-large-v3 (language={lang_iso})...")
        with open(temp_mp3, "rb") as f:
            files = {
                "file": (os.path.basename(temp_mp3), f, "audio/mp3")
            }
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
                timeout=120
            )

        resp.raise_for_status()
        res = resp.json()

        raw_segments = res.get("segments", [])
        segments = []
        for i, s in enumerate(raw_segments):
            start = s.get("start", 0.0)
            end = s.get("end", 0.0)
            duration = end - start
            segments.append({
                "id": i + 1,
                "text": s.get("text", "").strip(),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(duration, 3)
            })

        logger.info(f"Groq Whisper ASR completed: {len(segments)} segments")
        # Split long segments
        segments = split_long_segments(segments, max_duration=10.0)
        logger.info(f"After splitting: {len(segments)} segments")
        return segments
    except Exception as e:
        logger.error(f"Groq ASR failed: {e}", exc_info=True)
        return None
    finally:
        if os.path.exists(temp_mp3):
            try:
                os.remove(temp_mp3)
            except OSError:
                pass


def transcribe(audio_path: str, language: str) -> list[dict]:
    # Try Groq first
    groq_segments = transcribe_groq(audio_path, language)
    if groq_segments is not None:
        return groq_segments

    logger.warning("Groq ASR failed or was not configured. Falling back to Azure ASR...")
    azure_lang = "en-US" if language == "auto" else language
    speech_config = speechsdk.SpeechConfig(
        subscription=config.AZURE_SPEECH_KEY,
        region=config.AZURE_SPEECH_REGION,
    )
    speech_config.speech_recognition_language = azure_lang
    speech_config.request_word_level_timestamps()
    speech_config.output_format = speechsdk.OutputFormat.Detailed

    audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config,
    )

    segments = []
    done = False
    segment_id = 0
    errors = []

    def on_recognized(evt):
        nonlocal segment_id
        result = evt.result
        if result.reason == speechsdk.ResultReason.RecognizedSpeech and result.text.strip():
            start = result.offset / 10_000_000
            duration = result.duration / 10_000_000
            end = start + duration
            segment_id += 1
            segment = {
                "id": segment_id,
                "text": result.text,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(duration, 3),
            }
            segments.append(segment)
            logger.info(f"Segment {segment_id}: [{start:.1f}s-{end:.1f}s] {result.text[:50]}...")

    def on_canceled(evt):
        nonlocal done
        details = evt.result.cancellation_details
        if details.reason == speechsdk.CancellationReason.EndOfStream:
            logger.info("Recognition reached end of stream.")
        elif details.reason == speechsdk.CancellationReason.Error:
            error_msg = f"ASR error: {details.error_details}"
            logger.error(error_msg)
            errors.append(error_msg)
        else:
            logger.warning(f"Recognition canceled: {details.reason}")
        done = True

    def on_session_stopped(evt):
        nonlocal done
        logger.info("Recognition session stopped.")
        done = True

    recognizer.recognized.connect(on_recognized)
    recognizer.canceled.connect(on_canceled)
    recognizer.session_stopped.connect(on_session_stopped)

    logger.info(f"Starting transcription: {audio_path} (language: {language})")
    recognizer.start_continuous_recognition()

    while not done:
        time.sleep(0.5)

    recognizer.stop_continuous_recognition()

    if errors:
        raise RuntimeError(f"Transcription failed: {'; '.join(errors)}")

    logger.info(f"Transcription complete: {len(segments)} raw segments")

    # Split long segments into ~MAX_SEGMENT_DURATION chunks
    segments = split_long_segments(segments, max_duration=10.0)
    logger.info(f"After splitting: {len(segments)} segments")

    return segments


def split_long_segments(segments: list[dict], max_duration: float = 10.0) -> list[dict]:
    """Split segments longer than max_duration into smaller ones at sentence boundaries.

    Uses punctuation (. ! ? ;) to find split points. Distributes time
    proportionally based on character count.
    """
    import re
    result = []
    new_id = 0

    for seg in segments:
        if seg["duration"] <= max_duration:
            new_id += 1
            result.append({**seg, "id": new_id})
            continue

        # Split text at sentence boundaries
        sentences = re.split(r'(?<=[.!?;])\s+', seg["text"].strip())
        if len(sentences) <= 1:
            # No sentence boundary found, keep as-is
            new_id += 1
            result.append({**seg, "id": new_id})
            continue

        # Group sentences into chunks that fit within max_duration
        total_chars = sum(len(s) for s in sentences)
        total_duration = seg["duration"]
        start = seg["start"]

        chunk_sentences = []
        chunk_chars = 0

        for sentence in sentences:
            estimated_chunk_duration = (chunk_chars + len(sentence)) / total_chars * total_duration

            # If adding this sentence exceeds max_duration and we already have content, flush
            if chunk_sentences and estimated_chunk_duration > max_duration:
                chunk_duration = chunk_chars / total_chars * total_duration
                end = round(start + chunk_duration, 3)
                new_id += 1
                result.append({
                    "id": new_id,
                    "text": " ".join(chunk_sentences),
                    "start": round(start, 3),
                    "end": end,
                    "duration": round(chunk_duration, 3),
                })
                start = end
                chunk_sentences = []
                chunk_chars = 0

            chunk_sentences.append(sentence)
            chunk_chars += len(sentence)

        # Flush remaining
        if chunk_sentences:
            end = seg["end"]
            new_id += 1
            result.append({
                "id": new_id,
                "text": " ".join(chunk_sentences),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
            })

    return result


def save_transcript(segments: list[dict], output_path: str) -> str:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    logger.info(f"Transcript saved: {output_path}")
    return output_path
