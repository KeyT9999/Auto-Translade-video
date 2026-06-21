import os
import uuid
import logging
import threading
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import config
from pipeline_vi import run_pipeline_vi

# Setup FastAPI App
app = FastAPI(title="Auto-Translade-video AI UI")

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


from typing import Optional, Dict

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


def execute_pipeline(task_id: str, req: PipelineRequest):
    global tasks
    
    # Setup thread-specific logging capture
    log_list = []
    handler = TaskLogHandler(log_list)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    with tasks_lock:
        tasks[task_id] = {
            "status": "running",
            "progress_step": "STEP 1: Initializing",
            "logs": log_list,
            "result": None,
            "error": None
        }

    try:
        # Resolve voice ID from voice selection
        if req.voice == "male":
            voice_id = config.VIETNAMESE_VOICEID_MALE
        else:
            voice_id = config.VIETNAMESE_VOICEID_FEMALE

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


@app.post("/api/run")
def run_pipeline(req: PipelineRequest, background_tasks: BackgroundTasks):
    if not req.url and not req.file_path and not req.resume_dir:
        raise HTTPException(status_code=400, detail="Either video URL, local file path, or resume directory is required")
        
    task_id = str(uuid.uuid4())
    background_tasks.add_task(execute_pipeline, task_id, req)
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
def get_status(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)
        
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

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
        "status": task["status"],
        "progress_step": current_step,
        "result": task["result"],
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
