import os
import json
import pytest
from pipeline_vi import PipelineResult
from src.batch_runner import (
    BatchRunner,
    create_batch_state,
    load_batch_state,
    build_batch_report,
)

def _write_links_file(tmp_path, links):
    path = tmp_path / "links.txt"
    path.write_text("\n".join(links) + "\n", encoding="utf-8")
    return str(path)

def test_batch_runner_output_speed_propagation(tmp_path):
    links = ["https://www.tiktok.com/@demo/video/1"]
    path = _write_links_file(tmp_path, links)
    
    extra_options = {
        "output_playback_speed": 1.2
    }
    
    batch = create_batch_state(
        path,
        mode="subtitle_only",
        source_lang="en-US",
        output_root=str(tmp_path / "VN"),
        batch_output_dir=str(tmp_path / "batches"),
        extra_options=extra_options,
        delay_between_videos_seconds=0,
    )
    
    assert batch.extra_options["output_playback_speed"] == 1.2
    
    # Mock pipeline runner that writes a report with output speed info
    def fake_pipeline_runner(**kwargs):
        assert kwargs["extra_options"]["output_playback_speed"] == 1.2
        
        session_dir = tmp_path / "VN" / f"session_{kwargs['job_index']}"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Write dummy files
        rendered_video = session_dir / "subtitled_video_1.2x.mp4"
        rendered_video.write_bytes(b"video")
        
        report_path = session_dir / "report.json"
        report_data = {
            "output_dir": str(session_dir),
            "output_playback_speed": 1.2,
            "speed_adjusted": True,
            "files": {
                "rendered_video_original_speed": str(session_dir / "subtitled_video.mp4"),
                "rendered_video_final": str(rendered_video)
            }
        }
        report_path.write_text(json.dumps(report_data), encoding="utf-8")
        
        return PipelineResult(
            success=True,
            output_dir=str(session_dir),
            rendered_video=str(rendered_video),
            report_path=str(report_path),
            published_urls={"facebook": None, "youtube": None},
            error_step=None,
            error_type=None,
            error_message=None,
        )

    runner = BatchRunner(pipeline_runner=fake_pipeline_runner, sleeper=lambda _: None)
    runner.run(batch)
    
    # Reload and assert speed data is populated in Job
    persisted = load_batch_state(batch.batch_dir)
    job = persisted.jobs[0]
    assert job.output_playback_speed == 1.2
    assert job.speed_adjusted is True
    assert job.rendered_video_final.endswith("subtitled_video_1.2x.mp4")
    
    # Validate report serialization
    report = build_batch_report(persisted).to_dict()
    job_report = report["jobs"][0]
    assert job_report["output_playback_speed"] == 1.2
    assert job_report["speed_adjusted"] is True
    assert job_report["rendered_video_final"].endswith("subtitled_video_1.2x.mp4")
