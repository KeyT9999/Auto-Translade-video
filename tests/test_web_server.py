import os
import json
import pytest
from fastapi.testclient import TestClient
from web_server import app
import config

client = TestClient(app)

def test_speakers_endpoint(tmp_path):
    # Prepare dummy transcript_vi.json in a temp work dir
    work_dir = str(tmp_path)
    transcript_data = [
        {"id": 1, "text": "Hello", "text_vi": "Xin chào", "speaker": "NV_CHINH", "speaker_gender": "male"},
        {"id": 2, "text": "Hi", "text_vi": "Chào", "speaker": "NV_PHU", "speaker_gender": "female"},
        {"id": 3, "text": "Narration", "text_vi": "Dẫn chuyện", "speaker": "NARRATOR", "speaker_gender": "neutral"},
    ]
    
    transcript_path = os.path.join(work_dir, "transcript_vi.json")
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(transcript_data, f, ensure_ascii=False, indent=2)
        
    # Query /api/speakers
    response = client.get(f"/api/speakers?work_dir={work_dir}")
    assert response.status_code == 200
    data = response.json()
    
    speakers_list = data["speakers"]
    assert len(speakers_list) == 3
    
    speakers_map = {item["speaker"]: item["gender"] for item in speakers_list}
    assert speakers_map["NV_CHINH"] == "male"
    assert speakers_map["NV_PHU"] == "female"
    assert speakers_map["NARRATOR"] == "neutral"
    
    assert data["default_male"] == config.VIETNAMESE_VOICEID_MALE
    assert data["default_female"] == config.VIETNAMESE_VOICEID_FEMALE

def test_run_pipeline_missing_args():
    response = client.post("/api/run", json={"source_lang": "en-US"})
    assert response.status_code == 400
    assert "Either video URL, local file path, or resume directory is required" in response.json()["detail"]

def test_run_pipeline_with_url_success(monkeypatch):
    # Mock execute_pipeline to do nothing
    monkeypatch.setattr("web_server.execute_pipeline", lambda task_id, req: None)
    
    response = client.post("/api/run", json={
        "url": "https://www.youtube.com/watch?v=mock",
        "source_lang": "en-US",
        "pause_for_speakers": True,
        "burn_subtitles": True
    })
    assert response.status_code == 200
    assert "task_id" in response.json()


def test_run_batch_pipeline_missing_links():
    response = client.post("/api/batch/run", json={"links_text": "   "})
    assert response.status_code == 400
    assert "Batch mode requires 1-50 video links." in response.json()["detail"]


def test_run_batch_pipeline_success(monkeypatch):
    monkeypatch.setattr("web_server.execute_batch_pipeline", lambda task_id, req: None)

    response = client.post("/api/batch/run", json={
        "links_text": "https://www.douyin.com/video/1\nhttps://www.tiktok.com/@demo/video/2",
        "source_lang": "en-US",
        "mode": "subtitle_only",
    })
    assert response.status_code == 200
    assert "task_id" in response.json()


def test_get_voice_preview_endpoint(monkeypatch):
    called_synthesize = False
    
    def mock_synthesize(text_vi, output_path, voice_id):
        nonlocal called_synthesize
        called_synthesize = True
        with open(output_path, "wb") as f:
            f.write(b"dummy wav data")
        return {"path": output_path, "status": "generated"}
        
    import src.synthesizer_vi
    monkeypatch.setattr(src.synthesizer_vi, "synthesize_segment_vi", mock_synthesize)
    
    response = client.get("/api/voices/preview/female")
    assert response.status_code == 200
    assert response.content == b"dummy wav data"
    assert called_synthesize is True


def test_check_link_endpoint():
    # Setup temporary mockup output/VN/test_session
    session_dir = os.path.join("output", "VN", "test_check_link_session")
    os.makedirs(session_dir, exist_ok=True)
    
    report_data = {
        "status": "success",
        "source_url": "https://www.youtube.com/watch?v=test_check_link",
        "output_dir": session_dir,
        "files": {
            "dubbed_video": os.path.join(session_dir, "dubbed_video.mp4")
        }
    }
    
    report_path = os.path.join(session_dir, "report.json")
    video_path = os.path.join(session_dir, "dubbed_video.mp4")
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f)
            
        with open(video_path, "wb") as f:
            f.write(b"mock mp4 data")
            
        # Test GET endpoint
        response = client.get("/api/check-link?url=https://www.youtube.com/watch?v=test_check_link")
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert "work_dir" in data
        
        # Test GET endpoint with non-existent URL
        response = client.get("/api/check-link?url=https://www.youtube.com/watch?v=non_existent")
        assert response.status_code == 200
        assert response.json()["exists"] is False
        
    finally:
        # Cleanup
        if os.path.exists(report_path):
            os.remove(report_path)
        if os.path.exists(video_path):
            os.remove(video_path)
        if os.path.exists(session_dir):
            os.rmdir(session_dir)


