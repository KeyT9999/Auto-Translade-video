import sys
import os
import json
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.translation_validator import CJK_RE

def check_session(session_dir: str):
    print(f"=== Checking Translation Session: {session_dir} ===")
    
    if not os.path.exists(session_dir):
        print(f"Error: Session directory does not exist: {session_dir}")
        return

    transcript_vi_path = os.path.join(session_dir, "transcript_vi.json")
    if not os.path.exists(transcript_vi_path):
        print(f"Error: transcript_vi.json not found in {session_dir}")
        return
        
    try:
        with open(transcript_vi_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
        print(f"Loaded {len(segments)} segments from transcript_vi.json")
    except Exception as e:
        print(f"Error reading transcript_vi.json: {e}")
        return

    cjk_leaks = []
    empty_segments = []
    
    for s in segments:
        seg_id = s.get("id")
        text_vi = s.get("text_vi", s.get("dub_vi", s.get("literal_vi", "")))
        
        # Check CJK leak
        if CJK_RE.search(str(text_vi)):
            cjk_leaks.append((seg_id, text_vi))
            
        # Check empty
        if not text_vi or not str(text_vi).strip():
            empty_segments.append(seg_id)
            
    print(f"\nVerification Results:")
    if cjk_leaks:
        print(f"FAIL: Found {len(cjk_leaks)} CJK leaks:")
        for seg_id, text in cjk_leaks:
            print(f"  Segment {seg_id}: {text}")
    else:
        print("PASS: No CJK leaks found.")

    if empty_segments:
        print(f"FAIL: Found {len(empty_segments)} empty segments: {empty_segments}")
    else:
        print("PASS: No empty segments found.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/check_translation_session.py <session_dir>")
        sys.exit(1)
    check_session(sys.argv[1])
