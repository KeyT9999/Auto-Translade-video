import json

from src.batch_runner import (
    JOB_STATUS_FAILED,
    JOB_STATUS_PUBLISHED,
    JOB_STATUS_PUBLISH_FAILED,
    JOB_STATUS_SKIPPED_DUPLICATE,
    create_batch_state,
    save_batch_state,
    write_batch_reports,
)


def _write_links_file(tmp_path, links):
    path = tmp_path / "links.txt"
    path.write_text("\n".join(links) + "\n", encoding="utf-8")
    return str(path)


def test_batch_report_json_generated(tmp_path):
    path = _write_links_file(
        tmp_path,
        [
            "https://www.tiktok.com/@demo/video/1",
            "https://www.tiktok.com/@demo/video/2",
            "https://www.tiktok.com/@demo/video/1",
        ],
    )
    batch = create_batch_state(
        path,
        mode="subtitle_only",
        source_lang="zh-CN",
        output_root=str(tmp_path / "VN"),
        batch_output_dir=str(tmp_path / "batches"),
        publish_platforms=["facebook"],
        dry_run=True,
    )
    batch.started_at = "2026-06-22T13:25:00+07:00"
    batch.finished_at = "2026-06-22T13:30:00+07:00"
    batch.jobs[0].status = JOB_STATUS_PUBLISHED
    batch.jobs[0].output_dir = str(tmp_path / "VN" / "session_1")
    batch.jobs[0].rendered_video = str(tmp_path / "VN" / "session_1" / "subtitled_video.mp4")
    batch.jobs[0].published_urls["facebook"] = "https://www.facebook.com/watch/?v=123"
    batch.jobs[1].status = JOB_STATUS_FAILED
    batch.jobs[1].error_step = "translation"
    batch.jobs[1].error_message = "DeepSeek timeout"
    batch.jobs[2].status = JOB_STATUS_SKIPPED_DUPLICATE
    save_batch_state(batch)
    write_batch_reports(batch)

    report_path = tmp_path / "batches" / batch.batch_id / "batch_report.json"
    assert report_path.exists()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["batch_id"] == batch.batch_id
    assert payload["total_jobs"] == 3
    assert payload["published"] == 1
    assert payload["failed"] == 1
    assert payload["skipped_duplicate"] == 1
    assert payload["jobs"][1]["error_message"] == "DeepSeek timeout"


def test_batch_report_markdown_generated(tmp_path):
    path = _write_links_file(
        tmp_path,
        [
            "https://www.tiktok.com/@demo/video/1",
            "https://www.tiktok.com/@demo/video/2",
        ],
    )
    batch = create_batch_state(
        path,
        mode="subtitle_only",
        source_lang="zh-CN",
        output_root=str(tmp_path / "VN"),
        batch_output_dir=str(tmp_path / "batches"),
        publish_platforms=["facebook"],
        dry_run=True,
    )
    batch.jobs[0].status = JOB_STATUS_PUBLISH_FAILED
    batch.jobs[0].output_dir = str(tmp_path / "VN" / "session_1")
    batch.jobs[0].error_message = "Facebook token expired"
    batch.jobs[1].status = JOB_STATUS_PUBLISHED
    batch.jobs[1].output_dir = str(tmp_path / "VN" / "session_2")
    batch.jobs[1].published_urls["facebook"] = "https://www.facebook.com/watch/?v=456"
    save_batch_state(batch)
    write_batch_reports(batch)

    report_path = tmp_path / "batches" / batch.batch_id / "batch_report.md"
    assert report_path.exists()

    content = report_path.read_text(encoding="utf-8")
    assert f"# Batch Report: {batch.batch_id}" in content
    assert "| # | Status | URL | Output | Error |" in content
    assert "Facebook token expired" in content
