import sys
import os
import time
from pathlib import Path

# Fix console encoding for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Add src and current directory to Python path
sys.path.append(os.getcwd())

import config

# Force settings for the integration test
config.TTS_PROVIDER = "omnivoice"
config.OMNIVOICE_LOCAL_PORT = 3902  # Use a separate port for testing
config.VIETNAMESE_API_KEY = "local_offline"

from src.synthesizer_vi import synthesize_segment_vi, is_valid_audio_file

print("Starting integration test...")
print(f"Active provider: {config.TTS_PROVIDER}")
print(f"Local port: {config.OMNIVOICE_LOCAL_PORT}")

test_out = "scratch/integrated_output.wav"
if os.path.exists(test_out):
    os.remove(test_out)

try:
    # We will test using the 'YTB' profile from the user's database
    # It should automatically start the server, load the model, query the DB to resolve the YTB profile,
    # perform CUDA zero-shot voice cloning, write the WAV file, and clean up.
    print("\n--- Invoking synthesize_segment_vi with voice_id='YTB' ---")
    start_time = time.time()
    result = synthesize_segment_vi(
        text_vi="Xin chào, đây là bản thu âm thử nghiệm chạy trực tiếp từ chương trình dịch video tự động.",
        output_path=test_out,
        target_duration=8.0,
        voice_id="YTB"
    )
    duration = time.time() - start_time
    print(f"Synthesis completed in {duration:.2f} seconds!")
    print("Result dictionary:")
    for k, v in result.items():
         print(f"  {k}: {v}")
         
    if is_valid_audio_file(test_out):
         print(f"\nSUCCESS: Output file is a valid WAV audio of size {os.path.getsize(test_out)} bytes!")
    else:
         print("\nFAILURE: Output file is missing or invalid.")
         
except Exception as e:
    import traceback
    print("\nIntegration test encountered an error:")
    traceback.print_exc()

print("\n--- Script exiting. The atexit hook should shut down the sidecar server now. ---")
