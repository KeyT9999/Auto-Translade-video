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
config.OMNIVOICE_LOCAL_PORT = 3903  # Separate port for dialogue test
config.VIETNAMESE_API_KEY = "local_offline"

from src.synthesizer_vi import synthesize_segment_vi

dialogue_dir = Path("scratch/dialogue")
dialogue_dir.mkdir(exist_ok=True, parents=True)

# Dialogue text and speaker setup
script = [
    {"speaker": "YTB", "text": "Chào cậu, hôm nay thời tiết đẹp nhỉ? Cậu có định đi chơi đâu không?"},
    {"speaker": "MHY", "text": "Chào cậu! Ừ, trời đẹp thật đấy. Mình định đi dạo công viên một lát."},
    {"speaker": "YTB", "text": "Tuyệt vời quá! Vậy chúc cậu đi chơi vui vẻ nhé."},
    {"speaker": "MHY", "text": "Cảm ơn cậu nhiều nha, chúc cậu một ngày tốt lành!"}
]

print("Starting Dialogue Generation...")
print(f"Speaker A: YTB (cloned voice)")
print(f"Speaker B: MHY (cloned voice)")

audio_segments = []

try:
    for idx, turn in enumerate(script, start=1):
        speaker = turn["speaker"]
        text = turn["text"]
        out_path = dialogue_dir / f"turn_{idx}_{speaker}.wav"
        
        print(f"\n--- Synthesizing Turn {idx}: [{speaker}] -> '{text}' ---")
        start_time = time.time()
        
        result = synthesize_segment_vi(
            text_vi=text,
            output_path=str(out_path),
            voice_id=speaker
        )
        
        print(f"Completed in {time.time() - start_time:.2f}s (Duration: {result['actual_duration']}s)")
        
        # Load the synthesized audio
        audio_segments.append(AudioSegment.from_wav(str(out_path)))
        
    # Merge dialogue segments with a 500ms silence in between
    print("\nMerging turns into full dialogue...")
    silence = AudioSegment.silent(duration=500)  # 500ms silence
    
    full_audio = audio_segments[0]
    for seg in audio_segments[1:]:
        full_audio = full_audio + silence + seg
        
    full_dialogue_path = dialogue_dir / "full_dialogue.wav"
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
