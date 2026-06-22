import json
import os
import wave

import pytest
import requests

import pipeline_vi
import src.synthesizer_vi
from src.synthesizer_vi import TTSSegmentError, _download_audio


class _MockResponse:
    def __init__(self, status_code: int, chunks: list[bytes] | None = None, reason: str = "OK"):
        self.status_code = status_code
        self.reason = reason
        self._chunks = chunks or []
        self.headers = {"Content-Length": str(sum(len(chunk) for chunk in self._chunks))}

    def iter_content(self, chunk_size: int = 65536):
        yield from self._chunks

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"{self.status_code} {self.reason}",
                response=self,
            )


def _write_silence_wav(path: str, duration_ms: int = 300):
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * int(16 * duration_ms))


def _prepare_resume_dir(tmp_path, segment_count: int = 2) -> str:
    work_dir = tmp_path / "session"
    work_dir.mkdir()

    (work_dir / "demo.mp4").write_bytes(b"0")
    (work_dir / "original_audio.wav").write_bytes(b"0")

    original_segments = []
    translated_segments = []
    for idx in range(1, segment_count + 1):
        original_segments.append(
            {
                "id": idx,
                "text": f"source {idx}",
                "start": float(idx - 1),
                "end": float(idx),
                "duration": 1.0,
            }
        )
        translated_segments.append(
            {
                "id": idx,
                "text": f"source {idx}",
                "start": float(idx - 1),
                "end": float(idx),
                "duration": 1.0,
                "text_vi": f"Xin chào {idx}",
                "dub_vi": f"Xin chào {idx}",
                "final_dub_vi": f"Xin chào {idx}",
                "subtitle_vi": f"Xin chào {idx}",
                "speaker": "Em",
                "speaker_gender": "female",
            }
        )

    for name, payload in {
        "transcript_original.json": original_segments,
        "transcript_vi.json": translated_segments,
        "glossary.json": {"terms": {}},
        "character_bible.json": {"characters": [{"speaker_id": "Em", "vi_pronoun_self": "em", "vi_pronoun_other": "anh"}]},
        "video_context.json": {"video_type": "dialogue"},
    }.items():
        with open(work_dir / name, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    return str(work_dir)


def test_download_audio_retries_502_then_succeeds(monkeypatch, tmp_path):
    responses = [
        _MockResponse(502, reason="Bad Gateway"),
        _MockResponse(200, chunks=[b"fake-audio"]),
    ]

    monkeypatch.setattr(src.synthesizer_vi.requests, "get", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(src.synthesizer_vi, "is_valid_audio_file", lambda path: True)
    monkeypatch.setattr(src.synthesizer_vi.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(src.synthesizer_vi, "_refresh_audio_url_if_needed", lambda url, provider, export_id=None: url)

    output_path = str(tmp_path / "segment.download")
    result = _download_audio(output_path="{}".format(output_path), url="https://audio.test/file.wav", provider="lucylab", export_id="job_1")

    assert result["attempts"] == 2
    assert result["retry_count"] == 1
    assert os.path.exists(output_path)


def test_pipeline_writes_tts_pending_segments_when_segment_fails(monkeypatch, tmp_path):
    work_dir = _prepare_resume_dir(tmp_path, segment_count=1)

    monkeypatch.setattr(pipeline_vi, "is_valid_audio_file", lambda path: os.path.exists(path) and os.path.getsize(path) > 0)
    monkeypatch.setattr(pipeline_vi, "synthesize_segment_vi", lambda *a, **k: (_ for _ in ()).throw(
        TTSSegmentError(
            "502 Bad Gateway",
            provider="lucylab",
            job_id="job_failed",
            audio_url="https://audio.test/failed.wav",
            attempts=8,
        )
    ))

    report = pipeline_vi.run_pipeline_vi(
        url=None,
        file_path=None,
        source_lang="zh-CN",
        voice_id="voice_1",
        skip_video=True,
        output_dir=str(tmp_path),
        resume_dir=work_dir,
        bg_mode="none",
        mode="dub_audio",
    )

    assert report["status"] == "partial_failed"
    pending_path = os.path.join(work_dir, "tts_pending_segments.json")
    assert os.path.exists(pending_path)

    with open(pending_path, encoding="utf-8") as handle:
        pending = json.load(handle)

    assert pending["status"] == "partial_failed"
    assert pending["failed_segments"][0]["id"] == 1
    assert pending["failed_segments"][0]["job_id"] == "job_failed"


def test_resume_only_retries_missing_segment(monkeypatch, tmp_path):
    work_dir = _prepare_resume_dir(tmp_path, segment_count=2)
    tts_dir = os.path.join(work_dir, "tts_segments")
    os.makedirs(tts_dir, exist_ok=True)
    _write_silence_wav(os.path.join(tts_dir, "segment_0001.wav"))

    pending_path = os.path.join(work_dir, "tts_pending_segments.json")
    with open(pending_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "status": "partial_failed",
                "failed_segments": [{"id": 2, "error": "502 Bad Gateway"}],
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    monkeypatch.setattr(pipeline_vi, "is_valid_audio_file", lambda path: os.path.exists(path) and os.path.getsize(path) > 0)
    monkeypatch.setattr(pipeline_vi.config, "AUDIO_SLOW_FACTOR", 1.0)
    monkeypatch.setattr(pipeline_vi, "fit_segments_to_timeline", lambda segs, src, dst: [])
    monkeypatch.setattr(pipeline_vi, "merge_segments", lambda *a, **k: None)

    calls = []

    def mock_synthesize(text_vi, output_path, target_duration, voice_id):
        calls.append((text_vi, output_path, target_duration, voice_id))
        _write_silence_wav(output_path)
        return {
            "path": output_path,
            "actual_duration": 0.3,
            "speed_adjusted": False,
            "rate_applied": "1.0x",
            "provider": "lucylab",
            "voice_id": voice_id,
            "job_id": "job_ok",
            "audio_url": "https://audio.test/ok.wav",
            "retry_count": 0,
            "status": "generated",
        }

    monkeypatch.setattr(pipeline_vi, "synthesize_segment_vi", mock_synthesize)

    report = pipeline_vi.run_pipeline_vi(
        url=None,
        file_path=None,
        source_lang="zh-CN",
        voice_id="voice_1",
        skip_video=True,
        output_dir=str(tmp_path),
        resume_dir=work_dir,
        bg_mode="none",
        mode="dub_audio",
    )

    assert report["status"] == "success"
    assert len(calls) == 1
    assert "Xin chào 2" in calls[0][0]
    assert not os.path.exists(pending_path)
    assert report["tts_summary"]["cached_segment_ids"] == [1]
    assert report["tts_summary"]["new_segment_ids"] == [2]
