import os
import uuid
import json
import logging
import threading
from fastapi import FastAPI, BackgroundTasks, HTTPException, Response, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import config
from pipeline_vi import run_pipeline_vi
from src.batch_runner import (
    BatchRunner,
    build_batch_report,
    create_batch_state_from_links,
    load_batch_state,
    parse_links_text,
)

# Setup FastAPI App
app = FastAPI(title="Auto-Translate-video AI UI")

# Ensure output and static directories exist
os.makedirs("output", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Mount output folder to serve completed videos
app.mount("/output", StaticFiles(directory="output"), name="output")

# Memory store for task status and logs
tasks = {}
tasks_lock = threading.Lock()


class TaskLogHandler(logging.Handler):
    """Custom logging handler to capture logs in memory per task."""
    def __init__(self, log_list):
        super().__init__()
        self.log_list = log_list
        self.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S")
        )

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_list.append(msg)
        except Exception:
            self.handleError(record)


from typing import Optional, Dict, Any

class PipelineRequest(BaseModel):
    url: Optional[str] = None
    file_path: Optional[str] = None
    source_lang: str = "en-US"
    voice: str = "female"  # male or female
    bg_mode: str = "demucs"  # demucs, duck, none
    bg_duck_db: float = -12.0
    publish_youtube: bool = False
    publish_facebook: bool = False
    resume_dir: Optional[str] = None
    pause_for_speakers: bool = False
    speaker_map: Optional[Dict[str, str]] = None
    burn_subtitles: bool = False
    mode: Optional[str] = "dub_audio"
    cover_original_subtitles: bool = False
    subtitle_style: str = "plain"
    subtitle_font_size: Optional[int] = None
    mask_opacity: Optional[float] = None
    mask_y_percent: Optional[float] = None
    mask_height_percent: Optional[float] = None
    logo_path: Optional[str] = None
    logo_position: str = "top_right"
    logo_width: Optional[int] = None
    output_playback_speed: float = 1.0


class BatchPipelineRequest(BaseModel):
    links_text: str
    source_lang: str = "en-US"
    voice: str = "female"
    bg_mode: str = "demucs"
    bg_duck_db: float = -12.0
    publish_youtube: bool = False
    publish_facebook: bool = False
    burn_subtitles: bool = False
    mode: Optional[str] = "subtitle_only"
    cover_original_subtitles: bool = False
    subtitle_style: str = "plain"
    subtitle_font_size: Optional[int] = None
    mask_opacity: Optional[float] = None
    mask_y_percent: Optional[float] = None
    mask_height_percent: Optional[float] = None
    logo_path: Optional[str] = None
    logo_position: str = "top_right"
    logo_width: Optional[int] = None
    output_playback_speed: float = 1.0


def _build_batch_extra_options(req: BatchPipelineRequest) -> dict[str, Any]:
    return {
        "voice": req.voice,
        "skip_video": False,
        "bg_mode": req.bg_mode,
        "bg_duck_db": req.bg_duck_db,
        "burn_subtitles": req.burn_subtitles,
        "cover_original_subtitles": req.cover_original_subtitles,
        "subtitle_style": req.subtitle_style,
        "subtitle_font_size": req.subtitle_font_size,
        "mask_opacity": req.mask_opacity,
        "mask_y_percent": req.mask_y_percent,
        "mask_height_percent": req.mask_height_percent,
        "no_dub_audio": False,
        "logo_path": req.logo_path,
        "logo_position": req.logo_position,
        "logo_width": req.logo_width,
        "output_playback_speed": req.output_playback_speed,
    }


def _serialize_batch_snapshot(batch_dir: str) -> Optional[dict[str, Any]]:
    try:
        batch = load_batch_state(batch_dir)
    except Exception:
        return None

    report = build_batch_report(batch).to_dict()
    return {
        "kind": "batch",
        "batch_id": batch.batch_id,
        "batch_dir": batch.batch_dir,
        "links_file": batch.links_file,
        "report_json": os.path.join(batch.batch_dir, "batch_report.json"),
        "report_md": os.path.join(batch.batch_dir, "batch_report.md"),
        "mode": batch.mode,
        "jobs": report["jobs"],
        "summary": report,
    }


def execute_pipeline(task_id: str, req: PipelineRequest):
    global tasks
    from src.ai import ai_router
    ai_router.reset_failures()
    
    # Setup thread-specific logging capture
    log_list = []
    handler = TaskLogHandler(log_list)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    with tasks_lock:
        tasks[task_id] = {
            "task_kind": "single",
            "status": "running",
            "progress_step": "STEP 1: Initializing",
            "logs": log_list,
            "result": None,
            "error": None,
            "batch_dir": None,
        }

    try:
        # Resolve voice ID from voice selection
        if req.voice == "male":
            voice_id = config.VIETNAMESE_VOICEID_MALE
        elif req.voice == "female":
            voice_id = config.VIETNAMESE_VOICEID_FEMALE
        else:
            voice_id = req.voice

        # Ensure voice ID is configured only if mode is not subtitle_only
        if req.mode != "subtitle_only" and not voice_id:
            raise ValueError(f"Voice ID for '{req.voice}' is not configured in .env")

        # Run pipeline
        report = run_pipeline_vi(
            url=req.url,
            file_path=req.file_path,
            source_lang=req.source_lang,
            voice_id=voice_id or "",
            skip_video=False,
            output_dir=os.path.join(config.OUTPUT_DIR, "VN"),
            resume_dir=req.resume_dir,
            bg_mode=req.bg_mode,
            bg_duck_db=req.bg_duck_db,
            publish_youtube=req.publish_youtube,
            publish_facebook=req.publish_facebook,
            pause_for_speakers=req.pause_for_speakers,
            speaker_map=req.speaker_map,
            burn_subtitles=req.burn_subtitles,
            mode=req.mode or "dub_audio",
            cover_original_subtitles=req.cover_original_subtitles,
            subtitle_style=req.subtitle_style,
            subtitle_font_size=req.subtitle_font_size,
            mask_opacity=req.mask_opacity,
            mask_y_percent=req.mask_y_percent,
            mask_height_percent=req.mask_height_percent,
            logo_path=req.logo_path,
            logo_position=req.logo_position,
            logo_width=req.logo_width,
            output_playback_speed=req.output_playback_speed,
        )

        with tasks_lock:
            if isinstance(report, dict) and report.get("status") == "translate_pending":
                tasks[task_id]["status"] = "translate_pending"
                tasks[task_id]["progress_step"] = "STEP 4: Translation Pending"
                tasks[task_id]["result"] = report
            elif isinstance(report, dict) and report.get("status") == "speaker_pending":
                tasks[task_id]["status"] = "speaker_pending"
                tasks[task_id]["progress_step"] = "STEP 4.5: Speaker Pending"
                tasks[task_id]["result"] = report
            elif isinstance(report, dict) and report.get("status") == "partial_failed":
                tasks[task_id]["status"] = "partial_failed"
                tasks[task_id]["progress_step"] = "STEP 5: TTS Pending"
                tasks[task_id]["result"] = report
            else:
                tasks[task_id]["status"] = "success"
                tasks[task_id]["progress_step"] = "Completed"
                tasks[task_id]["result"] = report

    except Exception as e:
        root_logger.error(f"Task {task_id} failed: {e}", exc_info=True)
        with tasks_lock:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["progress_step"] = "Failed"
            tasks[task_id]["error"] = str(e)
    finally:
        root_logger.removeHandler(handler)


def execute_batch_pipeline(task_id: str, req: BatchPipelineRequest):
    global tasks
    from src.ai import ai_router
    ai_router.reset_failures()

    log_list = []
    handler = TaskLogHandler(log_list)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    with tasks_lock:
        tasks[task_id] = {
            "task_kind": "batch",
            "status": "running",
            "progress_step": "STEP 1: Initializing batch",
            "logs": log_list,
            "result": None,
            "error": None,
            "batch_dir": None,
        }

    try:
        links = parse_links_text(req.links_text)
        publish_platforms = []
        if req.publish_youtube:
            publish_platforms.append("youtube")
        if req.publish_facebook:
            publish_platforms.append("facebook")

        batch = create_batch_state_from_links(
            links,
            mode=req.mode or "subtitle_only",
            source_lang=req.source_lang,
            output_root=os.path.join(config.OUTPUT_DIR, "VN"),
            publish_platforms=publish_platforms,
            extra_options=_build_batch_extra_options(req),
        )

        with tasks_lock:
            tasks[task_id]["batch_dir"] = batch.batch_dir

        runner = BatchRunner()
        batch = runner.run(batch)
        result = _serialize_batch_snapshot(batch.batch_dir)
        summary = result["summary"] if result else None

        with tasks_lock:
            tasks[task_id]["status"] = (
                "partial_failed"
                if summary and (summary.get("failed") or summary.get("publish_failed"))
                else "success"
            )
            tasks[task_id]["progress_step"] = "Completed"
            tasks[task_id]["result"] = result

    except Exception as e:
        root_logger.error(f"Batch task {task_id} failed: {e}", exc_info=True)
        with tasks_lock:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["progress_step"] = "Failed"
            tasks[task_id]["error"] = str(e)
    finally:
        root_logger.removeHandler(handler)


@app.post("/api/upload-logo")
def upload_logo(file: UploadFile = File(...)):
    import time
    try:
        os.makedirs("output/logos", exist_ok=True)
        filename = f"{int(time.time())}_{file.filename}"
        save_path = os.path.join("output", "logos", filename)
        with open(save_path, "wb") as buffer:
            buffer.write(file.file.read())
        abs_path = os.path.abspath(save_path)
        return {"logo_path": abs_path}
    except Exception as e:
        logger = logging.getLogger("web_server")
        logger.error(f"Error uploading logo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def find_completed_session_by_url(url: str) -> Optional[dict[str, Any]]:
    from src.utils import extract_url
    clean_url = extract_url(url) if url else ""
    if not clean_url:
        return None

    vn_dir = os.path.join("output", "VN")
    if not os.path.exists(vn_dir):
        return None

    for entry in os.listdir(vn_dir):
        entry_path = os.path.join(vn_dir, entry)
        if os.path.isdir(entry_path):
            report_path = os.path.join(entry_path, "report.json")
            if os.path.exists(report_path):
                try:
                    with open(report_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    report_url = data.get("source_url")
                    if report_url:
                        from src.utils import extract_url as extract_report_url
                        report_url = extract_report_url(report_url)
                        
                    if report_url == clean_url and data.get("status") == "success":
                        # Validate that the video exists
                        files = data.get("files", {})
                        video_path = files.get("dubbed_video") or files.get("subtitled_video")
                        if video_path and os.path.exists(video_path):
                            return data
                except Exception:
                    pass
    return None


@app.get("/api/check-link")
def check_link(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter is required")
    session = find_completed_session_by_url(url)
    if session:
        return {
            "exists": True,
            "work_dir": session.get("output_dir"),
            "result": session
        }
    return {"exists": False}


@app.post("/api/run")
def run_pipeline(req: PipelineRequest, background_tasks: BackgroundTasks):
    if not req.url and not req.file_path and not req.resume_dir:
        raise HTTPException(status_code=400, detail="Either video URL, local file path, or resume directory is required")
    
    if req.url:
        from src.utils import extract_url
        req.url = extract_url(req.url)
        
    task_id = str(uuid.uuid4())
    background_tasks.add_task(execute_pipeline, task_id, req)
    return {"task_id": task_id}


@app.post("/api/batch/run")
def run_batch_pipeline(req: BatchPipelineRequest, background_tasks: BackgroundTasks):
    if not req.links_text or not req.links_text.strip():
        raise HTTPException(status_code=400, detail="Batch mode requires 1-50 video links.")

    try:
        parse_links_text(req.links_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    task_id = str(uuid.uuid4())
    background_tasks.add_task(execute_batch_pipeline, task_id, req)
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
def get_status(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)
        
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    batch_snapshot = None
    if task.get("task_kind") == "batch" and task.get("batch_dir"):
        batch_snapshot = _serialize_batch_snapshot(task["batch_dir"])

    # Figure out current step from logs
    current_step = task["progress_step"]
    for log in reversed(task["logs"]):
        if "STEP" in log:
            # Extract the step name
            parts = log.split("STEP")
            if len(parts) > 1:
                current_step = "STEP" + parts[1].split(" - ")[0].split("...")[0].strip()
                break

    return {
        "task_id": task_id,
        "task_kind": task.get("task_kind", "single"),
        "status": task["status"],
        "progress_step": current_step,
        "result": task["result"],
        "batch": batch_snapshot,
        "error": task["error"],
        "logs": task["logs"]
    }


@app.get("/api/speakers")
def get_speakers(work_dir: str):
    if not work_dir:
        raise HTTPException(status_code=400, detail="work_dir parameter is required")
        
    transcript_path = os.path.join(work_dir, "transcript_vi.json")
    if not os.path.exists(transcript_path):
        raise HTTPException(status_code=404, detail="transcript_vi.json not found in work directory")
        
    try:
        import json
        with open(transcript_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read transcript: {e}")
        
    speakers = {}
    for s in segments:
        sp_name = s.get("speaker")
        if sp_name:
            speakers[sp_name] = s.get("speaker_gender", "neutral")
            
    result = [{"speaker": k, "gender": v} for k, v in speakers.items()]
    return {
        "speakers": result,
        "work_dir": work_dir,
        "default_male": getattr(config, "VIETNAMESE_VOICEID_MALE", ""),
        "default_female": getattr(config, "VIETNAMESE_VOICEID_FEMALE", ""),
    }


@app.get("/api/voices")
def get_voices():
    voices = []
    
    # 1. Standard system presets
    voices.append({"id": "female", "name": "Giọng Nữ mặc định", "gender": "female", "source": "system"})
    voices.append({"id": "male", "name": "Giọng Nam mặc định", "gender": "male", "source": "system"})
    
    # TikTok Voices
    voices.append({"id": "BV074_streaming", "name": "TikTok: Cô gái hoạt ngôn (Nữ)", "gender": "female", "source": "tiktok"})
    voices.append({"id": "BV075_streaming", "name": "TikTok: Giọng Nam", "gender": "male", "source": "tiktok"})
    
    # 2. Cloned voices from OmniVoice Studio SQLite DB
    roaming_app = os.environ.get("APPDATA", "")
    db_path = os.path.join(roaming_app, "OmniVoice", "omnivoice.db")
    if os.path.exists(db_path):
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT id, name, ref_text, language FROM voice_profiles ORDER BY name ASC")
            for row in c.fetchall():
                vid, vname, vtext, vlang = row
                voices.append({
                    "id": vid,
                    "name": f"Clone: {vname}",
                    "gender": "neutral",
                    "source": "omnivoice",
                    "ref_text": vtext,
                    "language": vlang
                })
            conn.close()
        except Exception as e:
            logging.error(f"Error querying SQLite voice profiles: {e}")
            
    # 3. Local voices folder in Auto-Translade-video & parent directories
    search_dirs = [("voices", "local_file"), ("..", "parent_dir"), ("../voices", "parent_voices")]
    for s_dir, source_name in search_dirs:
        if os.path.exists(s_dir):
            try:
                for f_name in os.listdir(s_dir):
                    if os.path.isfile(os.path.join(s_dir, f_name)) and f_name.lower().endswith((".wav", ".mp3")):
                        # Avoid duplicates
                        if not any(v["id"] == f_name for v in voices):
                            display_name = f"File: {f_name}"
                            if "0623" in f_name:
                                display_name = "Giọng mới (0623)"
                            voices.append({
                                "id": f_name,
                                "name": display_name,
                                "gender": "neutral",
                                "source": source_name
                            })
            except Exception as e:
                logging.error(f"Error scanning directory {s_dir}: {e}")
                
    return {"voices": voices, "provider": config.TTS_PROVIDER}


@app.get("/api/voices/preview/{voice_id}")
def get_voice_preview(voice_id: str):
    if "0623" in voice_id or voice_id in ("37862b30", "hue.mp3"):
        text = "Xin chào! Đây là lần đầu tiên tôi trò chuyện bằng giọng nói mới được nhân bản trực tiếp từ tệp âm thanh mẫu."
    else:
        text = "Xin chào, đây là giọng đọc thử nghiệm của tôi."
    
    from src.synthesizer_vi import synthesize_segment_vi
    import tempfile
    
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, f"preview_{uuid.uuid4().hex}.wav")
    
    try:
        resolved_voice_id = voice_id
        if voice_id == "female":
            resolved_voice_id = config.VIETNAMESE_VOICEID_FEMALE
        elif voice_id == "male":
            resolved_voice_id = config.VIETNAMESE_VOICEID_MALE
            
        res = synthesize_segment_vi(
            text_vi=text,
            output_path=output_path,
            voice_id=resolved_voice_id or ""
        )
        
        if os.path.exists(output_path):
            with open(output_path, "rb") as f:
                content = f.read()
            try:
                os.remove(output_path)
            except OSError:
                pass
            return Response(content=content, media_type="audio/wav")
        else:
            raise HTTPException(status_code=500, detail="TTS succeeded but output file not found")
    except Exception as e:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        raise HTTPException(
            status_code=500,
            detail=f"Không thể tạo âm thanh nghe thử: {e}"
        )



@app.get("/")
def serve_ui():
    """Fallback index page if not served via static files directly."""
    static_index = os.path.join("static", "index.html")
    if os.path.exists(static_index):
        with open(static_index, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Web UI index.html not found in static/</h1>")


# Serve other static files
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    # Start web server on port 8000
    uvicorn.run("web_server:app", host="127.0.0.1", port=8000, reload=True)
