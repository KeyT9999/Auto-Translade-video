import sys
import os
import io
import argparse
from typing import Optional
from pathlib import Path
from pydantic import BaseModel

# 1. Parse port argument
parser = argparse.ArgumentParser(description="OmniVoice Local Sidecar Server")
parser.add_argument("--port", type=int, default=3901, help="Port to run the server on")
args, unknown = parser.parse_known_args()

# 2. Redirect HuggingFace cache to the same folder OmniVoice Studio uses
local_app = os.environ.get("LOCALAPPDATA", "")
short_cache = os.path.join(local_app, "OmniVoice", "hf_cache")
os.environ["HF_HOME"] = short_cache
os.environ["HF_HUB_CACHE"] = short_cache

# 3. Add OmniVoice-Studio to path so we can import its modules
sys.path.append(r"d:\MMO\OmniVoice-Studio")

import uvicorn
from fastapi import FastAPI, Response, BackgroundTasks

app = FastAPI(title="OmniVoice Local Sidecar Server")
model = None
torch = None
torchaudio = None
OmniVoice = None

class SynthesizeRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    speed: Optional[float] = 1.0
    target_duration: Optional[float] = None

def resolve_voice(voice_id: Optional[str]):
    if not voice_id:
        return None, None
        
    # If voice_id is a direct path to a file, check if it exists
    if os.path.exists(voice_id):
        return voice_id, ""
        
    roaming_app = os.environ.get("APPDATA", "")
    db_path = os.path.join(roaming_app, "OmniVoice", "omnivoice.db")
    voices_dir = os.path.join(roaming_app, "OmniVoice", "voices")
    
    # Try querying SQLite voice_profiles table
    if os.path.exists(db_path):
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            # Match by ID or Name (case-insensitive)
            c.execute(
                "SELECT ref_audio_path, ref_text FROM voice_profiles WHERE id = ? OR name = ? COLLATE NOCASE",
                (voice_id, voice_id)
            )
            row = c.fetchone()
            conn.close()
            if row:
                ref_audio_name, ref_text = row
                full_path = os.path.join(voices_dir, ref_audio_name)
                if os.path.exists(full_path):
                    print(f"[OmniVoice Server] Resolved profile '{voice_id}' -> {full_path}")
                    return full_path, ref_text
                else:
                    print(f"[OmniVoice Server] Warning: Database matched voice '{voice_id}' but audio file not found at: {full_path}")
        except Exception as e:
            print(f"[OmniVoice Server] Database lookup error: {e}")
            
    # Fallback to file name match directly in the voices directory
    fallback_path = os.path.join(voices_dir, voice_id)
    if os.path.exists(fallback_path):
        return fallback_path, ""
    for ext in ['.wav', '.mp3', '.MP3', '.WAV']:
        if os.path.exists(fallback_path + ext):
            return fallback_path + ext, ""
            
    # Try local folder, parent folder (..), and parent voices folder (../voices)
    search_dirs = ["voices", "..", "../voices"]
    for s_dir in search_dirs:
        # Check direct match in directory
        direct_match = os.path.join(s_dir, voice_id)
        if os.path.exists(direct_match):
            return direct_match, ""
        # Check match with extensions
        for ext in ['.wav', '.mp3', '.MP3', '.WAV']:
            match_with_ext = direct_match + ext
            if os.path.exists(match_with_ext):
                return match_with_ext, ""

    print(f"[OmniVoice Server] Could not resolve voice profile or path: '{voice_id}'")
    return None, None

@app.on_event("startup")
def startup_event():
    global model, torch, torchaudio, OmniVoice
    print("[OmniVoice Server] Bootstrapping PyTorch and OmniVoice...")
    import torch as _torch
    import torchaudio as _torchaudio
    from omnivoice.models.omnivoice import OmniVoice as _OmniVoice  # type: ignore

    
    torch = _torch
    torchaudio = _torchaudio
    OmniVoice = _OmniVoice
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[OmniVoice Server] Loading model on device: {device}")
    
    checkpoint = "k2-fsa/OmniVoice"
    model = OmniVoice.from_pretrained(
        checkpoint, device_map=device, dtype=torch.float16, load_asr=False
    )
    print("[OmniVoice Server] Model loaded and ready for synthesis!")

@app.get("/ping")
def ping():
    if model is not None:
        return {"status": "ready"}
    return {"status": "loading"}

@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    if model is None:
        return Response(content="Model not loaded yet", status_code=503)
        
    try:
        ref_audio, ref_text = resolve_voice(req.voice_id)
        
        gen_kw = dict(
            text=req.text,
            language="Vietnamese",
            num_step=16,
            guidance_scale=2.0,
            speed=req.speed or 1.0,
            duration=req.target_duration,
            denoise=True
        )
        
        if ref_audio:
            print(f"[OmniVoice Server] Synthesizing segment with voice clone: {ref_audio}")
            audios = model.generate(ref_audio=ref_audio, ref_text=ref_text or "", **gen_kw)
        else:
            print("[OmniVoice Server] Synthesizing segment with default voice (no clone)")
            audios = model.generate(**gen_kw)
            
        waveform = audios[0].cpu()
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)
            
        buffer = io.BytesIO()
        torchaudio.save(buffer, waveform, getattr(model, "sampling_rate", 24000), format="wav")
        
        return Response(content=buffer.getvalue(), media_type="audio/wav")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response(content=f"Synthesis failed: {e}", status_code=500)

@app.post("/shutdown")
def shutdown(background_tasks: BackgroundTasks):
    global model
    print("[OmniVoice Server] Received shutdown request. Cleaning up memory...")
    model = None
    if torch is not None and torch.cuda.is_available():
        import gc
        gc.collect()
        torch.cuda.empty_cache()
        
    def exit_now():
        import time
        time.sleep(0.5)
        print("[OmniVoice Server] Process terminating.")
        os._exit(0)
        
    background_tasks.add_task(exit_now)
    return {"status": "shutting_down"}

if __name__ == "__main__":
    print(f"[OmniVoice Server] Starting FastAPI on port {args.port}...")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
