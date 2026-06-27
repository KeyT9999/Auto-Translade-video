import sys
import os
import time
from pathlib import Path
from pydub import AudioSegment

# Fix console encoding for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Add src and current directory to Python path
sys.path.append(os.getcwd())

import config

# Set configuration to use local omnivoice provider
config.TTS_PROVIDER = "omnivoice"
config.OMNIVOICE_LOCAL_PORT = 3904  # Separate port for 0623 test
config.VIETNAMESE_API_KEY = "local_offline"

from src.synthesizer_vi import synthesize_segment_vi

dialogue_dir = Path("scratch/dialogue_0623")
dialogue_dir.mkdir(exist_ok=True, parents=True)

# Dialogue text and speaker setup
# Speaker A uses the direct path to the new voice D:\MMO\0623.WAV
# Speaker B uses the YTB voice profile
script = [
    {"speaker": r"d:\MMO\0623.WAV", "name": "New Voice (0623)", "text": "Xin chào! Đây là lần đầu tiên tôi trò chuyện bằng giọng nói mới được nhân bản trực tiếp từ tệp âm thanh mẫu."},
    {"speaker": "YTB", "name": "YTB Voice", "text": "Chào bạn! Nghe giọng mới của bạn rất hay và tự nhiên đấy. Công nghệ nhân bản này thật tuyệt vời."},
    {"speaker": r"d:\MMO\0623.WAV", "name": "New Voice (0623)", "text": "Đúng vậy! Rất nhanh và tiện lợi, không cần huấn luyện phức tạp chút nào cả."},
    {"speaker": "YTB", "name": "YTB Voice", "text": "Tuyệt quá. Chúc bạn có nhiều sản phẩm video dịch và lồng tiếng chất lượng cao nhé!"}
]

print("Starting Dialogue Generation...")
print(f"Speaker A: {script[0]['name']} (Path: {script[0]['speaker']})")
print(f"Speaker B: {script[1]['name']} (Database name: {script[1]['speaker']})")

audio_segments = []

try:
    for idx, turn in enumerate(script, start=1):
        voice_id = turn["speaker"]
        name = turn["name"]
        text = turn["text"]
        out_path = dialogue_dir / f"turn_{idx}_{name.replace(' ', '_')}.wav"
        
        print(f"\n--- Synthesizing Turn {idx}: [{name}] -> '{text}' ---")
        start_time = time.time()
        
        result = synthesize_segment_vi(
            text_vi=text,
            output_path=str(out_path),
            voice_id=voice_id
        )
        
        print(f"Completed in {time.time() - start_time:.2f}s (Duration: {result['actual_duration']}s)")
        
        # Load the synthesized audio
        audio_segments.append(AudioSegment.from_wav(str(out_path)))
        
    # Merge dialogue segments with a 600ms silence in between
    print("\nMerging turns into full dialogue...")
    silence = AudioSegment.silent(duration=600)  # 600ms silence
    
    full_audio = audio_segments[0]
    for seg in audio_segments[1:]:
        full_audio = full_audio + silence + seg
        
    full_dialogue_path = dialogue_dir / "full_dialogue_0623.wav"
    full_audio.export(str(full_dialogue_path), format="wav")
    
    print(f"\nSUCCESS: Dialogue exported successfully!")
    print(f"Saved at: {full_dialogue_path.resolve()}")
    print(f"Total duration: {len(full_audio)/1000:.2f} seconds")
    print(f"File size: {full_dialogue_path.stat().st_size / 1024:.2f} KB")

except Exception as e:
    import traceback
    print("\nDialogue generation failed:")
    traceback.print_exc()

print("\n--- Script complete, shutting down local server... ---")
