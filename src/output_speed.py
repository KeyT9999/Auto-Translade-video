import os
import re
import json
import subprocess

def validate_output_speed(speed: float) -> float:
    try:
        speed = float(speed)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid playback speed: {speed}. Must be a float.")
    
    allowed = [1.0, 1.1, 1.2, 1.3]
    if speed not in allowed:
        raise ValueError(f"Playback speed {speed} not allowed. Supported options: {allowed}")
    return speed

def build_speed_suffix(speed: float) -> str:
    if speed == 1.0:
        return ""
    return f"_{speed}x"

def _has_audio_stream(video_path: str) -> bool:
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "default=nw=1:nk=1",
            video_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return "audio" in res.stdout.strip().lower()
    except Exception:
        # Fallback: assume has audio if probe fails
        return True

def apply_playback_speed_to_video(input_video: str, output_video: str, speed: float, overwrite: bool = True) -> str:
    speed = validate_output_speed(speed)
    if speed == 1.0:
        if os.path.abspath(input_video) != os.path.abspath(output_video):
            import shutil
            shutil.copy2(input_video, output_video)
        return output_video

    has_audio = _has_audio_stream(input_video)
    if has_audio:
        filter_complex = f"[0:v]setpts=PTS/{speed}[v];[0:a]atempo={speed}[a]"
        cmd = [
            "ffmpeg",
            "-y" if overwrite else "-n",
            "-i", input_video,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "superfast",
            "-crf", "22",
            "-c:a", "aac",
            output_video
        ]
    else:
        filter_complex = f"[0:v]setpts=PTS/{speed}[v]"
        cmd = [
            "ffmpeg",
            "-y" if overwrite else "-n",
            "-i", input_video,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-c:v", "libx264",
            "-preset", "superfast",
            "-crf", "22",
            output_video
        ]

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg speed adjustment failed: {res.stderr}")
    return output_video

def _parse_srt_timestamp(ts: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+),(\d+)", ts.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp format: {ts}")
    h, m, s, ms = map(int, match.groups())
    return h * 3600.0 + m * 60.0 + s + ms / 1000.0

def _format_srt_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        ms -= 1000
        s += 1
    if s >= 60:
        s -= 60
        m += 1
    if m >= 60:
        m -= 60
        h += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def adjust_srt_for_speed(input_srt: str, output_srt: str, speed: float) -> str:
    speed = validate_output_speed(speed)
    if speed == 1.0:
        if os.path.abspath(input_srt) != os.path.abspath(output_srt):
            import shutil
            shutil.copy2(input_srt, output_srt)
        return output_srt

    with open(input_srt, "r", encoding="utf-8") as f:
        content = f.read()

    # Match SRT blocks: index, timestamp line, text
    pattern = re.compile(r"(\d+)\r?\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\r?\n(.*?)(?=\r?\n\r?\n|\Z)", re.DOTALL)
    matches = list(pattern.finditer(content))

    adjusted_blocks = []
    for m in matches:
        index = m.group(1)
        start_ts = m.group(2)
        end_ts = m.group(3)
        text = m.group(4)

        start_sec = _parse_srt_timestamp(start_ts) / speed
        end_sec = _parse_srt_timestamp(end_ts) / speed

        new_start = _format_srt_timestamp(start_sec)
        new_end = _format_srt_timestamp(end_sec)

        adjusted_blocks.append(f"{index}\n{new_start} --> {new_end}\n{text}\n\n")

    with open(output_srt, "w", encoding="utf-8") as f:
        f.writelines(adjusted_blocks)
    return output_srt

def _parse_ass_timestamp(ts: str) -> float:
    parts = ts.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid ASS timestamp format: {ts}")
    h = int(parts[0])
    m = int(parts[1])
    s_parts = parts[2].split(".")
    s = int(s_parts[0])
    cs = int(s_parts[1]) if len(s_parts) > 1 else 0
    return h * 3600.0 + m * 60.0 + s + cs / 100.0

def _format_ass_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs -= 100
        s += 1
    if s >= 60:
        s -= 60
        m += 1
    if m >= 60:
        m -= 60
        h += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def adjust_ass_for_speed(input_ass: str, output_ass: str, speed: float) -> str:
    speed = validate_output_speed(speed)
    if speed == 1.0:
        if os.path.abspath(input_ass) != os.path.abspath(output_ass):
            import shutil
            shutil.copy2(input_ass, output_ass)
        return output_ass

    with open(input_ass, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    adjusted_lines = []
    for line in lines:
        if line.startswith("Dialogue:"):
            # Dialogue: Marked,0:00:01.00,0:00:03.50,Style,,0,0,0,,Text
            parts = line.split(",", 9)
            if len(parts) >= 10:
                start_sec = _parse_ass_timestamp(parts[1]) / speed
                end_sec = _parse_ass_timestamp(parts[2]) / speed
                parts[1] = _format_ass_timestamp(start_sec)
                parts[2] = _format_ass_timestamp(end_sec)
                line = ",".join(parts)
        adjusted_lines.append(line)

    with open(output_ass, "w", encoding="utf-8-sig") as f:
        f.writelines(adjusted_lines)
    return output_ass

def adjust_transcript_json_for_speed(input_json: str, output_json: str, speed: float) -> str:
    speed = validate_output_speed(speed)
    if speed == 1.0:
        if os.path.abspath(input_json) != os.path.abspath(output_json):
            import shutil
            shutil.copy2(input_json, output_json)
        return output_json

    with open(input_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    def scale_segment(seg):
        if "start" in seg:
            seg["start"] = round(seg["start"] / speed, 3)
        if "end" in seg:
            seg["end"] = round(seg["end"] / speed, 3)
        if "duration" in seg:
            seg["duration"] = round(seg["duration"] / speed, 3)
        return seg

    if isinstance(data, list):
        data = [scale_segment(seg) for seg in data]
    elif isinstance(data, dict):
        if "segments" in data:
            data["segments"] = [scale_segment(seg) for seg in data["segments"]]
        else:
            for k, v in data.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and ("start" in v[0]):
                    data[k] = [scale_segment(seg) for seg in v]

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return output_json
