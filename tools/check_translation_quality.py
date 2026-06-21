"""check_translation_quality.py — CLI tool to check the translation quality of a completed session."""
import argparse
import json
import os
import re
import sys

# Add root directory to python path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure stdout/stderr use UTF-8 on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from src.translation_validator import validate_translation, CJK_RE, AWKWARD_PHRASES


def main():
    parser = argparse.ArgumentParser(description="Check translation quality for a session directory.")
    parser.add_argument("session_dir", help="Path to the VN session directory (e.g. output/VN/20260621103000_vi)")
    args = parser.parse_args()

    session_dir = args.session_dir
    if not os.path.exists(session_dir):
        print(f"ERROR: Session directory not found: {session_dir}")
        sys.exit(1)

    transcript_path = os.path.join(session_dir, "transcript_vi.json")
    if not os.path.exists(transcript_path):
        print(f"ERROR: transcript_vi.json not found in {session_dir}")
        sys.exit(1)

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse {transcript_path}: {e}")
        sys.exit(1)

    print("=" * 60)
    print(f"Checking quality for session: {os.path.basename(session_dir)}")
    print(f"Total Segments: {len(segments)}")
    print("=" * 60)

    quality_report = validate_translation(segments)
    
    issues = quality_report["issues"]
    errors = [iss for iss in issues if iss["severity"] == "error"]
    warnings = [iss for iss in issues if iss["severity"] == "warning"]

    print(f"Validation Status: {'FAILED' if errors else 'PASSED'}")
    print(f"Bad Segments: {quality_report['bad_segments']}")
    print(f"Total Issues Found: {len(issues)} (Errors: {len(errors)}, Warnings: {len(warnings)})")
    print("-" * 60)

    if issues:
        print("Detailed Issues:")
        for idx, iss in enumerate(issues, 1):
            sev_prefix = "🔴 ERROR" if iss["severity"] == "error" else "🟡 WARNING"
            print(f" {idx}. [{sev_prefix}] Segment {iss['id']}: {iss['type']}")
            print(f"    Message: {iss['message']}")
            if iss['text']:
                print(f"    Text:    \"{iss['text']}\"")
            print("-" * 40)
    else:
        print("🎉 No translation issues found!")

    print("=" * 60)

    # Check other context artifacts
    context_files = [
        "video_context.json",
        "character_bible.json",
        "glossary.json",
        "translation_quality_report.json",
        "translation_repair_report.json"
    ]
    
    print("Artifacts Checklist:")
    for f in context_files:
        path = os.path.join(session_dir, f)
        exists = "✅ Present" if os.path.exists(path) else "❌ Missing"
        print(f" - {f:<30} : {exists}")
    
    print("=" * 60)

    if errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
