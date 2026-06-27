import os
import glob

tutuaz_dir = r"d:\MMO\tutuaz"

print("Searching for files containing 'voice' or 'audio' or 'dub' in filenames...")
for root, dirs, files in os.walk(tutuaz_dir):
    # Skip .venv
    if ".venv" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            fpath = os.path.join(root, f)
            relpath = os.path.relpath(fpath, tutuaz_dir)
            
            # Read first few lines or search for key concepts
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as file:
                    content = file.read()
                    
                keywords = ["voice", "ref_audio", "clone", "speaker", "audio_path", "synthesize", "demucs"]
                matches = [kw for kw in keywords if kw in content.lower()]
                if matches:
                    print(f"- {relpath} (matches: {matches}, size: {os.path.getsize(fpath)} bytes)")
            except Exception as e:
                pass
