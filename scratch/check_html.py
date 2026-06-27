import sys
import os
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

html_path = Path("static/index.html")
print(f"Checking HTML at: {html_path}")

if html_path.exists():
    try:
        text = html_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"Error reading: {e}")
        sys.exit(1)
        
    print(f"Total size: {len(text)} characters")
    
    # Search for keywords
    keywords = ["Giọng", "voice", "Nữ", "Nam", "Speakers"]
    for kw in keywords:
        count = text.lower().count(kw.lower())
        print(f"Keyword '{kw}': found {count} times")
        
    # Print lines containing "giọng" or "voice"
    print("\n--- Matching lines for 'giong' or 'voice': ---")
    lines = text.splitlines()
    found = 0
    for idx, line in enumerate(lines, start=1):
        if "giọng" in line.lower() or "voice" in line.lower() or "gender" in line.lower():
            print(f"Line {idx}: {line.strip()[:120]}")
            found += 1
            if found >= 30:
                print("... and more matches.")
                break
else:
    print("HTML file does not exist.")
