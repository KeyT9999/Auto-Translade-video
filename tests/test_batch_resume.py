from pipeline_vi import PipelineResult
from src.batch_runner import (
    BatchRunner,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_PUBLISHED,
    JOB_STATUS_PUBLISH_FAILED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCESS,
    create_batch_state,
    save_batch_state,
)


def _write_links_file(tmp_path, links):
    path = tmp_path / "links.txt"
    path.write_text("\n".join(links) + "\n", encoding="utf-8")
    return str(path)


def _build_pipeline_result(session_dir):
    session_dir.mkdir(parents=True, exist_ok=True)
    rendered_video = session_dir / "subtitled_video.mp4"
    rendered_video.write_bytes(b"video")
    return PipelineResult(
        success=True,
        output_dir=str(session_dir),
        rendered_video=str(rendered_video),
        report_path=str(session_dir / "report.json"),
        published_urls={"facebook": None, "youtube": None},
        error_step=None,
        error_type=None,
        error_message=None,
    )


def test_resume_skips_success_jobs(tmp_path):
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
    batch.jobs[0].status = JOB_STATUS_SUCCESS
    batch.jobs[0].output_dir = str(tmp_path / "VN" / "existing_success")
    save_batch_state(batch)

    call_order = []

    def fake_pipeline_runner(**kwargs):
        call_order.append(kwargs["source_url"])
        return _build_pipeline_result(tmp_path / "VN" / f"session_{kwargs['job_index']}")

    runner = BatchRunner(pipeline_runner=fake_pipeline_runner, sleeper=lambda _: None)
    runner.run(batch)

    assert call_order == links[1:]


def test_retry_failed_jobs_only(tmp_path):
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
    batch.jobs[0].status = JOB_STATUS_SUCCESS
    batch.jobs[1].status = JOB_STATUS_FAILED
    batch.jobs[1].attempts = 1
    batch.jobs[2].status = JOB_STATUS_PUBLISHED
    save_batch_state(batch)

    call_order = []

    def fake_pipeline_runner(**kwargs):
        call_order.append(kwargs["source_url"])
        return _build_pipeline_result(tmp_path / "VN" / "retried_failed")

    runner = BatchRunner(pipeline_runner=fake_pipeline_runner, sleeper=lambda _: None)
    runner.run(batch, retry_failed=True)

    assert call_order == [links[1]]
    assert batch.jobs[1].status == JOB_STATUS_SUCCESS


def test_retry_publish_only_jobs_only(tmp_path):
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
        publish_platforms=["facebook"],
        delay_between_videos_seconds=0,
    )
    batch.jobs[0].status = JOB_STATUS_PUBLISHED
    batch.jobs[0].output_dir = str(tmp_path / "VN" / "already_published")
    batch.jobs[1].status = JOB_STATUS_PUBLISH_FAILED
    batch.jobs[1].output_dir = str(tmp_path / "VN" / "needs_publish_retry")
    batch.jobs[2].status = JOB_STATUS_FAILED
    batch.jobs[2].output_dir = str(tmp_path / "VN" / "failed_pipeline")
    save_batch_state(batch)

    publish_calls = []

    def fake_publish_runner(session_dir, platform):
        publish_calls.append((session_dir, platform))
        return {
            "success": True,
            "url": "https://www.facebook.com/watch/?v=123",
            "video_path": str(tmp_path / "VN" / "needs_publish_retry" / "subtitled_video.mp4"),
        }

    runner = BatchRunner(
        pipeline_runner=lambda **kwargs: _build_pipeline_result(tmp_path / "VN" / "unused"),
        publish_runner=fake_publish_runner,
        sleeper=lambda _: None,
    )
    runner.run(batch, retry_publish_platforms=["facebook"])

    assert publish_calls == [(batch.jobs[1].output_dir, "facebook")]
    assert batch.jobs[1].status == JOB_STATUS_PUBLISHED
    assert batch.jobs[2].status == JOB_STATUS_FAILED


def test_resume_recovers_interrupted_running_jobs(tmp_path):
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
        delay_between_videos_seconds=0,
    )
    batch.jobs[0].status = JOB_STATUS_RUNNING
    save_batch_state(batch)

    call_order = []

    def fake_pipeline_runner(**kwargs):
        call_order.append(kwargs["source_url"])
        return _build_pipeline_result(tmp_path / "VN" / f"session_{kwargs['job_index']}")

    runner = BatchRunner(pipeline_runner=fake_pipeline_runner, sleeper=lambda _: None)
    runner.run(batch)

    assert call_order == links
    assert batch.jobs[0].status == JOB_STATUS_SUCCESS
    assert batch.jobs[1].status == JOB_STATUS_SUCCESS
