import json
import os

from pipeline_vi import PipelineResult
from src.batch_runner import (
    BatchRunner,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_SKIPPED_DUPLICATE,
    JOB_STATUS_SUCCESS,
    create_batch_id,
    create_batch_state,
    load_batch_state,
    parse_links_file,
)


def _write_links_file(tmp_path, links):
    path = tmp_path / "links.txt"
    path.write_text("\n".join(links) + "\n", encoding="utf-8")
    return str(path)


def _build_pipeline_result(
    session_dir,
    *,
    success=True,
    rendered=None,
    error_step=None,
    error_type=None,
    error_message=None,
):
    session_dir.mkdir(parents=True, exist_ok=True)
    rendered = success if rendered is None else rendered
    rendered_video = session_dir / "subtitled_video.mp4"
    if rendered:
        rendered_video.write_bytes(b"video")
    report_path = session_dir / "report.json"
    report_path.write_text(json.dumps({"output_dir": str(session_dir)}), encoding="utf-8")
    return PipelineResult(
        success=success,
        output_dir=str(session_dir),
        rendered_video=str(rendered_video) if rendered else None,
        report_path=str(report_path),
        published_urls={"facebook": None, "youtube": None},
        error_step=error_step,
        error_type=error_type,
        error_message=error_message,
    )


def test_parse_links_file_with_one_link(tmp_path):
    path = _write_links_file(tmp_path, ["https://www.tiktok.com/@demo/video/1"])
    links = parse_links_file(path)
    assert links == ["https://www.tiktok.com/@demo/video/1"]


def test_parse_links_file_with_fifty_links(tmp_path):
    links = [f"https://www.tiktok.com/@demo/video/{index}" for index in range(50)]
    path = _write_links_file(tmp_path, links)
    assert len(parse_links_file(path)) == 50


def test_parse_links_file_rejects_zero_links(tmp_path):
    path = _write_links_file(tmp_path, [])
    try:
        parse_links_file(path)
    except ValueError as exc:
        assert "0 links" in str(exc)
    else:
        raise AssertionError("Expected ValueError for empty links file")


def test_parse_links_file_rejects_fifty_one_links(tmp_path):
    links = [f"https://www.tiktok.com/@demo/video/{index}" for index in range(51)]
    path = _write_links_file(tmp_path, links)
    try:
        parse_links_file(path)
    except ValueError as exc:
        assert "exceeds the maximum 50" in str(exc)
    else:
        raise AssertionError("Expected ValueError for more than 50 links")


def test_create_batch_id_has_expected_format():
    batch_id = create_batch_id()
    assert batch_id.startswith("batch_")
    assert len(batch_id) == len("batch_20260622_132500")


def test_skip_duplicate_links_marks_later_jobs(tmp_path):
    path = _write_links_file(
        tmp_path,
        [
            "https://www.douyin.com/video/123",
            "https://www.douyin.com/video/123",
            "https://v.douyin.com/abc",
        ],
    )
    batch = create_batch_state(
        path,
        mode="subtitle_only",
        source_lang="zh-CN",
        output_root=str(tmp_path / "VN"),
        batch_output_dir=str(tmp_path / "batches"),
        dry_run=True,
    )

    assert batch.jobs[0].status == JOB_STATUS_PENDING
    assert batch.jobs[1].status == JOB_STATUS_SKIPPED_DUPLICATE
    assert "Duplicate of job 001" in batch.jobs[1].error_message
    assert batch.jobs[2].status == JOB_STATUS_PENDING


def test_execute_jobs_sequentially(tmp_path):
    links = [
        "https://www.tiktok.com/@demo/video/1",
        "https://www.tiktok.com/@demo/video/2",
        "https://www.tiktok.com/@demo/video/3",
    ]
    path = _write_links_file(tmp_path, links)
    batch = create_batch_state(
        path,
        mode="subtitle_only",
        source_lang="zh-CN",
        output_root=str(tmp_path / "VN"),
        batch_output_dir=str(tmp_path / "batches"),
        delay_between_videos_seconds=0,
    )

    call_order = []

    def fake_pipeline_runner(**kwargs):
        call_order.append(kwargs["source_url"])
        session_dir = tmp_path / "VN" / f"session_{kwargs['job_index']}"
        return _build_pipeline_result(session_dir)

    runner = BatchRunner(pipeline_runner=fake_pipeline_runner, sleeper=lambda _: None)
    runner.run(batch)

    assert call_order == links
    assert [job.status for job in batch.jobs] == [JOB_STATUS_SUCCESS, JOB_STATUS_SUCCESS, JOB_STATUS_SUCCESS]

    persisted = load_batch_state(batch.batch_dir)
    assert persisted.jobs[0].status == JOB_STATUS_SUCCESS


def test_continue_after_one_job_fails(tmp_path):
    links = [
        "https://www.tiktok.com/@demo/video/1",
        "https://www.tiktok.com/@demo/video/2",
    ]
    path = _write_links_file(tmp_path, links)
    batch = create_batch_state(
        path,
        mode="subtitle_only",
        source_lang="zh-CN",
        output_root=str(tmp_path / "VN"),
        batch_output_dir=str(tmp_path / "batches"),
        continue_on_error=True,
        stop_on_error=False,
        delay_between_videos_seconds=0,
    )

    call_order = []

    def fake_pipeline_runner(**kwargs):
        call_order.append(kwargs["source_url"])
        session_dir = tmp_path / "VN" / f"session_{kwargs['job_index']}"
        if kwargs["job_index"] == 1:
            return _build_pipeline_result(
                session_dir,
                success=False,
                error_step="translation",
                error_type="TRANSLATION_FAILED",
                error_message="DeepSeek timeout",
            )
        return _build_pipeline_result(session_dir)

    runner = BatchRunner(pipeline_runner=fake_pipeline_runner, sleeper=lambda _: None)
    runner.run(batch)

    assert call_order == links
    assert batch.jobs[0].status == JOB_STATUS_FAILED
    assert batch.jobs[1].status == JOB_STATUS_SUCCESS


def test_stop_on_error_when_enabled(tmp_path):
    links = [
        "https://www.tiktok.com/@demo/video/1",
        "https://www.tiktok.com/@demo/video/2",
    ]
    path = _write_links_file(tmp_path, links)
    batch = create_batch_state(
        path,
        mode="subtitle_only",
        source_lang="zh-CN",
        output_root=str(tmp_path / "VN"),
        batch_output_dir=str(tmp_path / "batches"),
        continue_on_error=False,
        stop_on_error=True,
        delay_between_videos_seconds=0,
    )

    call_order = []

    def fake_pipeline_runner(**kwargs):
        call_order.append(kwargs["source_url"])
        session_dir = tmp_path / "VN" / f"session_{kwargs['job_index']}"
        return _build_pipeline_result(
            session_dir,
            success=False,
            error_step="translation",
            error_type="TRANSLATION_FAILED",
            error_message="DeepSeek timeout",
        )

    runner = BatchRunner(pipeline_runner=fake_pipeline_runner, sleeper=lambda _: None)
    runner.run(batch)

    assert call_order == [links[0]]
    assert batch.jobs[0].status == JOB_STATUS_FAILED
    assert batch.jobs[1].status == JOB_STATUS_PENDING


def test_parse_links_file_with_raw_sharing_text(tmp_path):
    path = _write_links_file(
        tmp_path,
        [
            "7.64 10/29 :1pm O@x.SY kCH:/ 紫藤花开，思念的人会如期归来。 https://v.douyin.com/RhbRuqdworA/ 复制此链接",
            "This line has no URL and should be ignored",
            "# This is a comment and should be ignored",
            "https://v.douyin.com/another_link/ 1.23 abc",
        ]
    )
    links = parse_links_file(path)
    assert links == [
        "https://v.douyin.com/RhbRuqdworA/",
        "https://v.douyin.com/another_link/"
    ]
