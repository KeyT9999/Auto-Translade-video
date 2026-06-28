import os
import glob
from datetime import datetime

def find_videos():
    pattern = os.path.join(r"d:\MMO\Auto-Translade-video\output\VN", "**", "subtitled_video.mp4")
    files = glob.glob(pattern, recursive=True)
    
    print("Found subtitled videos:")
    for f in files:
        stat = os.stat(f)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"Path: {f}\nSize: {stat.st_size} bytes\nModified: {mtime}\n")

if __name__ == "__main__":
    find_videos()
