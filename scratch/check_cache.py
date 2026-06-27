import os
from pathlib import Path

bin_dir = Path(r"d:\MMO\OmniVoice-Studio\bin")
for f in bin_dir.iterdir():
    size = f.stat().st_size
    print(f"File: {f.name}, Size: {size} bytes ({size / 1024 / 1024:.2f} MB)")
    if size < 1000 and f.is_file():
        try:
            print("Content:")
            print(f.read_text(errors='ignore'))
        except Exception as e:
            print(f"Error reading: {e}")
