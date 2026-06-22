import json
import os

from src.publish_existing import publish_existing_session


def _write_session_files(tmp_path):
    session_dir = tmp_path / "20260622095230_vi"
    session_dir.mkdir()

    report = {
        "session_id": "20260622095230_vi",
        "published_urls": {"youtube": None, "facebook": None},
        "files": {
            "dubbed_video": str(session_dir / "subtitled_video.mp4"),
            "youtube_metadata": str(session_dir / "youtube_metadata.json"),
        },
    }
    (session_dir / "subtitled_video.mp4").write_bytes(b"fake video bytes")
    (session_dir / "youtube_metadata.json").write_text(
        json.dumps(
            {
                "title": "Test title",
                "description": "Test description",
                "hashtags": ["#a", "#b"],
            }
        ),
        encoding="utf-8",
    )
    (session_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return session_dir


def test_publish_existing_video_updates_report_on_success(tmp_path, monkeypatch):
    session_dir = _write_session_files(tmp_path)

    called = {}

    def mock_publish(video_path, title, description):
        called["video_path"] = video_path
        called["title"] = title
        called["description"] = description
        return {
            "success": True,
            "platform": "facebook",
            "url": "https://www.facebook.com/watch/?v=123",
            "error": None,
            "phase": "complete",
        }

    monkeypatch.setattr("src.publish_existing.publish_to_facebook_detailed", mock_publish)

    result = publish_existing_session(str(session_dir), "facebook")

    assert result["success"] is True
    assert os.path.samefile(called["video_path"], session_dir / "subtitled_video.mp4")
    assert called["title"] == "Test title"
    assert called["description"] == "Test description"

    report = json.loads((session_dir / "report.json").read_text(encoding="utf-8"))
    assert report["published_urls"]["facebook"] == "https://www.facebook.com/watch/?v=123"
    assert report["publish_status"]["facebook"] == "success"
    assert "facebook" not in report.get("publish_error", {})


def test_publish_existing_video_updates_report_on_failure(tmp_path, monkeypatch):
    session_dir = _write_session_files(tmp_path)

    def mock_publish(video_path, title, description):
        return {
            "success": False,
            "platform": "facebook",
            "url": None,
            "error": "OAuthException code 190 subcode 463",
            "phase": "start",
        }

    monkeypatch.setattr("src.publish_existing.publish_to_facebook_detailed", mock_publish)

    result = publish_existing_session(str(session_dir), "facebook")

    assert result["success"] is False

    report = json.loads((session_dir / "report.json").read_text(encoding="utf-8"))
    assert report["publish_status"]["facebook"] == "failed"
    assert report["publish_error"]["facebook"] == "OAuthException code 190 subcode 463"
