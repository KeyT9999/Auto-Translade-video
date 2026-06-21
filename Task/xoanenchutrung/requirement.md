# REQUIREMENT: Che phụ đề gốc & Render phụ đề Việt có nền (Subtitle Cover + ASS Renderer)

## 1. Tổng quan vấn đề

### Hiện trạng
Pipeline hiện tại ở chế độ `subtitle_only` sử dụng FFmpeg `subtitles=` filter với file `.srt` đơn giản để burn phụ đề tiếng Việt vào video. Cách này có 3 vấn đề nghiêm trọng:

1. **Chữ Trung/phụ đề gốc vẫn hiển thị** — video gốc từ Douyin/TikTok thường đã hardsub sẵn phụ đề tiếng Trung. Khi burn thêm phụ đề Việt, cả 2 lớp chữ cùng hiển thị → khó đọc, thiếu chuyên nghiệp.
2. **Phụ đề Việt xấu** — SRT chỉ hỗ trợ styling rất cơ bản, không kiểm soát được font, viền, shadow, vị trí chính xác, nền phía sau chữ.
3. **Không che được vùng phụ đề cũ** — không có cơ chế nào để vẽ vùng nền tối mờ che phụ đề gốc trước khi render chữ Việt lên.

### Mục tiêu
Thêm option mới cho pipeline:
- **Che phụ đề gốc** bằng drawbox FFmpeg (vùng nền tối mờ ở phía dưới video)
- **Render phụ đề Việt đẹp** bằng file `.ass` (Advanced SubStation Alpha) thay vì `.srt`
- **Chữ Việt có nền/viền** rõ ràng, dễ đọc trên cả video dọc TikTok/Douyin lẫn video ngang YouTube
- **Giữ nguyên audio gốc** trong subtitle-only mode

## 2. Yêu cầu Chức năng

### 2.1 Tham số mới

#### CLI
```bash
python pipeline_vi.py --subtitle-only --cover-original-subtitles --subtitle-style boxed
```

| Tham số CLI | Giá trị | Mặc định | Mô tả |
|---|---|---|---|
| `--cover-original-subtitles` | flag (bool) | `false` | Bật vùng che phụ đề gốc |
| `--subtitle-style` | `boxed` / `plain` | `plain` | `boxed` = chữ có nền rounded, `plain` = chỉ chữ + outline |

#### API Schema (`PipelineRequest`)
```python
cover_original_subtitles: bool = False
subtitle_style: str = "plain"  # "boxed" hoặc "plain"
```

#### Config / .env (tùy chọn nâng cao)
```env
# Vùng che phụ đề gốc (tính theo % kích thước video)
SUBTITLE_MASK_Y_PERCENT=0.82        # vị trí Y bắt đầu (82% từ trên = khu dưới cùng)
SUBTITLE_MASK_HEIGHT_PERCENT=0.18   # chiều cao vùng che (18% video height)
SUBTITLE_MASK_OPACITY=0.55          # Độ mờ nền che (0.0 → 1.0)

# Style phụ đề ASS
SUBTITLE_FONT_NAME=Arial
SUBTITLE_FONT_SIZE=48
SUBTITLE_FONT_COLOR=&HFFFFFF       # Trắng
SUBTITLE_OUTLINE_SIZE=2
SUBTITLE_SHADOW_SIZE=1
SUBTITLE_BOX_OPACITY=0.6           # Opacity nền box phía sau chữ (chỉ dùng khi style=boxed)
SUBTITLE_MARGIN_BOTTOM=60          # Khoảng cách từ dưới video (pixel)
SUBTITLE_MAX_CHARS_PER_LINE=24     # Giới hạn ký tự mỗi dòng (video dọc cần ngắn hơn)
```

### 2.2 Web UI

Khi người dùng chọn mode **"Chỉ phụ đề (Subtitle Only)"** ở Step 2, hiển thị thêm một nhóm cấu hình phụ đề:

```
┌──────────────────────────────────────────┐
│ Cấu hình phụ đề                         │
│                                          │
│ [✓] Burn phụ đề vào video               │ ← checkbox, mặc định checked
│ [✓] Che phụ đề gốc (Cover original)     │ ← checkbox, mặc định unchecked
│                                          │
│ Kiểu phụ đề:  [ Chữ có nền ▾ ]         │ ← dropdown: "Chữ có nền" / "Chỉ chữ"
│ Cỡ chữ:       [ Vừa ▾ ]                 │ ← dropdown: Nhỏ (36) / Vừa (48) / Lớn (56)
│ Độ mờ nền:    [ ====●==== ] 0.55        │ ← range slider 0.3 – 0.9
└──────────────────────────────────────────┘
```

- Nhóm này **chỉ hiện** khi mode = `subtitle_only`.
- Khi mode = `dub_audio`, nhóm này **ẩn**.
- Checkbox "Burn phụ đề vào video" map sang field `burn_subtitles`.
- Checkbox "Che phụ đề gốc" map sang field `cover_original_subtitles`.
- Dropdown "Kiểu phụ đề" map sang field `subtitle_style` (`boxed` / `plain`).

### 2.3 Module mới: `src/subtitle_renderer.py`

Module này chịu trách nhiệm:

#### Function 1: `generate_ass_subtitles(segments, output_path, style_config)`
- Nhận danh sách segments đã dịch (JSON).
- Tạo file `.ass` với style đẹp cho phụ đề Việt.
- Hỗ trợ 2 style: `boxed` (có nền rounded phía sau chữ) và `plain` (chỉ chữ + outline đen).
- Field ưu tiên cho text: `subtitle_vi > final_dub_vi > dub_vi > text_vi > literal_vi`.
- Tự động xuống dòng nếu text quá dài (tối đa 2 dòng).
- Đảm bảo giữ đúng dấu tiếng Việt khi xuống dòng.

ASS Style cần đạt:
- Font: Arial hoặc tương đương (có sẵn trên mọi hệ thống).
- Chữ trắng, viền đen 2px, shadow nhẹ 1px.
- Căn giữa (Alignment 2 = bottom-center).
- Nếu `boxed`: thêm `BorderStyle=4` (opaque box background) với bo góc.
- Tối đa 2 dòng, vị trí dưới video.
- Tương thích tốt với video dọc TikTok/Douyin (9:16).

#### Function 2: `render_video_with_cover(input_video, ass_path, output_path, cover_config)`
- Sử dụng FFmpeg để render video output.
- Nếu `cover_original_subtitles = True`:
  ```
  ffmpeg -i input.mp4 -vf "drawbox=x=0:y=ih*0.82:w=iw:h=ih*0.18:color=black@0.55:t=fill,ass=transcript_vi.ass" -c:a copy output.mp4
  ```
- Nếu `cover_original_subtitles = False`:
  ```
  ffmpeg -i input.mp4 -vf "ass=transcript_vi.ass" -c:a copy output.mp4
  ```
- Audio: `-c:a copy` (giữ nguyên), fallback sang `-c:a aac` nếu copy lỗi.
- Video: `-c:v libx264 -preset veryfast -crf 22`.

### 2.4 Tích hợp vào Pipeline (`pipeline_vi.py`)

Cập nhật Step 7 (subtitle_only branch):

```python
# Step 7: Creating subtitled video (subtitle_only mode)
if burn_subtitles:
    # 1. Generate ASS file
    ass_path = generate_ass_subtitles(segments, os.path.join(work_dir, "transcript_vi.ass"), style_config)
    
    # 2. Render video with cover + ASS
    render_video_with_cover(video_path, ass_path, subtitled_video_path, cover_config)
else:
    # Chỉ copy video gốc
    shutil.copy2(video_path, subtitled_video_path)
```

Không thay đổi gì ở flow `dub_audio` — mode cũ giữ nguyên 100%.

### 2.5 Report Output

Khi chạy `subtitle_only` + `cover_original_subtitles`, file `report.json` cần ghi thêm:

```json
{
  "mode": "subtitle_only",
  "subtitle_burned": true,
  "cover_original_subtitles": true,
  "subtitle_style": "boxed",
  "files": {
    "transcript_vi_ass": "path/to/transcript_vi.ass",
    "dubbed_video": "path/to/subtitled_video.mp4",
    "audio_vi_full": null
  }
}
```

## 3. Yêu cầu Phi Chức năng

### 3.1 Tương thích ngược
- Mode `dub_audio` **KHÔNG** bị ảnh hưởng bởi bất kỳ thay đổi nào.
- Mode `subtitle_only` khi KHÔNG bật `cover_original_subtitles` vẫn hoạt động như cũ (burn SRT đơn giản).
- Tất cả test cases hiện tại phải pass.

### 3.2 Logging
Pipeline phải ghi log rõ ràng:
```
INFO - Generating ASS subtitles (style=boxed, cover=True)
INFO - Applying subtitle cover box: y=82%, h=18%, opacity=0.55
INFO - Rendering subtitled video with cover + ASS → subtitled_video.mp4
```

### 3.3 Error Handling
- Nếu FFmpeg render lỗi: raise RuntimeError với stderr rõ ràng, **không silent fail**.
- Nếu file ASS tạo lỗi: log warning và fallback về SRT burn cũ.

### 3.4 Font & Encoding
- File ASS phải dùng encoding UTF-8 BOM (`\ufeff`) theo chuẩn ASS.
- Font phải là font phổ biến có sẵn (Arial, Helvetica, Noto Sans).
- Đảm bảo hiển thị đúng dấu tiếng Việt: ă, â, ê, ô, ơ, ư, đ, và tất cả dấu thanh.

### 3.5 Video dọc (TikTok/Douyin)
- Với video 9:16, cỡ chữ cần lớn hơn bình thường vì màn hình hẹp.
- `max_chars_per_line` mặc định 24 (thay vì 42 của SRT) cho video dọc.
- Vùng che phụ đề gốc cần cover khoảng 18% phía dưới (phụ đề Trung thường ở vùng 82%-100% chiều cao).

## 4. Acceptance Criteria

| # | Tiêu chí | Cách kiểm chứng |
|---|---|---|
| 1 | UI có option "Che phụ đề gốc" | Mở web UI, chọn Subtitle Only, thấy checkbox |
| 2 | CLI có `--cover-original-subtitles` | Chạy `python pipeline_vi.py --help` |
| 3 | Pipeline tạo được `transcript_vi.ass` | Kiểm tra file output trong work_dir |
| 4 | Video output có khung nền che chữ Trung | Xem video, vùng dưới có nền tối mờ |
| 5 | Chữ Việt nằm trên nền, rõ, đẹp, dễ đọc | So sánh screenshot trước/sau |
| 6 | Audio gốc giữ nguyên | Kiểm tra audio stream với ffprobe |
| 7 | Mode dubbing cũ không bị ảnh hưởng | Chạy full test suite |
| 8 | Log rõ ràng | Kiểm tra console output |
| 9 | FFmpeg lỗi → báo lỗi rõ | Test với file input không hợp lệ |

## 5. Tham khảo Kỹ thuật

### FFmpeg drawbox syntax
```
drawbox=x=0:y=ih*0.82:w=iw:h=ih*0.18:color=black@0.55:t=fill
```

### ASS Subtitle Format (BorderStyle=4 = Opaque Box)
```
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: VietSub,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,4,2,1,2,20,20,60,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 0,0:00:01.00,0:00:03.50,VietSub,,0,0,0,,Cô ấy dạy\Nmình làm bảng
```

### Field Priority cho text render
```python
SUBTITLE_TEXT_FIELDS = ["subtitle_vi", "final_dub_vi", "dub_vi", "text_vi", "literal_vi"]
```

## 6. Files cần tạo/sửa

| File | Hành động | Mô tả |
|---|---|---|
| `src/subtitle_renderer.py` | **MỚI** | Module tạo ASS + render video với cover |
| `config.py` | THÊM | Các biến config subtitle mới |
| `pipeline_vi.py` | SỬA | Thêm params CLI, tích hợp renderer vào Step 7 |
| `web_server.py` | SỬA | Thêm fields API schema |
| `static/index.html` | SỬA | Thêm UI nhóm cấu hình phụ đề |
| `tests/test_subtitle_renderer.py` | **MỚI** | Unit tests cho ASS generation + render logic |
