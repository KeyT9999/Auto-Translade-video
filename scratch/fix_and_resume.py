import os
import json
import sys

# Reconfigure stdout to use UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add root directory to sys.path so we can import src modules
sys.path.append(os.path.abspath("d:/MMO/Auto-Translade-video"))

from src.translation_validator import validate_translation, has_blocking_errors
from src.contextual_translator import _merge_segment_translation
from src.srt_generator import generate_srt

work_dir = "d:/MMO/Auto-Translade-video/output/VN/20260627235906_vi"
windows_dir = os.path.join(work_dir, "translation_windows")

# 1. Load original segments
orig_path = os.path.join(work_dir, "transcript_original.json")
with open(orig_path, "r", encoding="utf-8") as f:
    orig_segments = json.load(f)

# 2. Load window translations
files = [
    "window_0001_0035.json",
    "window_0036_0070.json",
    "window_0071_0105.json",
    "window_0106_0125.json"
]

raw_results_by_id = {}
for filename in files:
    path = os.path.join(windows_dir, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            win_segments = json.load(f)
            for item in win_segments:
                raw_results_by_id[int(item["id"])] = item

# 3. Merge them
merged_segments = []
for orig in orig_segments:
    seg_id = int(orig["id"])
    if seg_id in raw_results_by_id:
        res = raw_results_by_id[seg_id]
        merged = _merge_segment_translation(orig, res)
        merged_segments.append(merged)

# 4. Apply overrides to fix blocking errors
overrides = {
    44: "Lại đây.",
    60: "Anh đang chuẩn bị quà cho em.",
    80: "Anh muốn đổi tùy anh.",
    81: "Em không đổi tùy em.",
    103: "Muốn thì em giúp anh nằm."
}

for seg in merged_segments:
    seg_id = int(seg["id"])
    if seg_id in overrides:
        new_text = overrides[seg_id]
        print(f"Overriding segment {seg_id}: '{seg['text_vi']}' -> '{new_text}'")
        seg["literal_vi"] = new_text
        seg["dub_vi"] = new_text
        seg["text_vi"] = new_text
        seg["subtitle_vi"] = new_text
        seg["final_dub_vi"] = new_text

# 5. Load glossary
glossary_path = os.path.join(work_dir, "glossary.json")
glossary = {}
if os.path.exists(glossary_path):
    with open(glossary_path, "r", encoding="utf-8") as f:
        glossary = json.load(f)

# 6. Validate
report = validate_translation(
    merged_segments,
    output_path=None,
    mode="dub_audio",
    source_language="zh-CN",
    glossary=glossary
)

print(f"\nValidation result:")
print(f"  Bad segments: {report['bad_segments']}")
print(f"  Blocking segments: {report['blocking_segments']}")
print(f"  Warning segments: {report['warning_segments']}")

for issue in report["issues"]:
    if issue.get("blocking"):
        print(f"  [BLOCKING] Segment {issue['id']}: {issue['message']}")

if not has_blocking_errors(report):
    print("\nNo blocking errors! Saving final transcript files...")
    
    # Save transcript_vi.json
    vi_json_path = os.path.join(work_dir, "transcript_vi.json")
    with open(vi_json_path, "w", encoding="utf-8") as f:
        json.dump(merged_segments, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {vi_json_path}")
    
    # Save transcript_vi.srt
    vi_srt_path = os.path.join(work_dir, "transcript_vi.srt")
    generate_srt(merged_segments, vi_srt_path, text_field="subtitle_vi")
    print(f"  Saved: {vi_srt_path}")
    
    # Delete TRANSLATE_PENDING.txt if exists
    pending_txt_path = os.path.join(work_dir, "TRANSLATE_PENDING.txt")
    if os.path.exists(pending_txt_path):
        os.remove(pending_txt_path)
        print(f"  Removed: {pending_txt_path}")
        
    print("\nSUCCESS! You can now resume the pipeline by running:")
    print(f"python pipeline_vi.py --resume \"{work_dir}\"")
else:
    print("\nFAILED: There are still blocking errors. Files were not written.")
