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
    else:
        print(f"File not found: {path}")

# 3. Merge them
merged_segments = []
for orig in orig_segments:
    seg_id = int(orig["id"])
    if seg_id in raw_results_by_id:
        res = raw_results_by_id[seg_id]
        merged = _merge_segment_translation(orig, res)
        merged_segments.append(merged)
    else:
        print(f"Missing translation for segment ID {seg_id}")

print(f"Merged segments: {len(merged_segments)}")

# 4. Load glossary
glossary_path = os.path.join(work_dir, "glossary.json")
glossary = {}
if os.path.exists(glossary_path):
    with open(glossary_path, "r", encoding="utf-8") as f:
        glossary = json.load(f)

# 5. Validate
report = validate_translation(
    merged_segments,
    output_path=None,
    mode="dub_audio",
    source_language="zh-CN",
    glossary=glossary
)

print(f"Total segments: {report['total_segments']}")
print(f"Bad segments: {report['bad_segments']}")
print(f"Blocking segments: {report['blocking_segments']}")
for issue in report["issues"]:
    if issue.get("blocking"):
        print(f"\nBLOCKING ISSUE:")
        print(f"  ID: {issue['id']}")
        print(f"  Text: {issue['text']}")
        print(f"  Message: {issue['message']}")
