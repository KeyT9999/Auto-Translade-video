# Yêu cầu phát triển Chế độ Chỉ dịch & Gắn phụ đề (Subtitle-only / No Dub Audio Mode)

## 1. Bối cảnh hiện tại

Hiện tại, hệ thống lồng tiếng video tự động chủ yếu đi theo hướng lồng tiếng đè âm thanh (dubbing):
```text
download/input video
→ extract audio
→ ASR (Whisper/Azure)
→ translate (Gemini/Llama)
→ TTS (LucyLab/LarVoice/Azure)
→ fit timeline (atempo/stretch)
→ mix audio (ghép đè thoại lên BGM)
→ render dubbed_video.mp4
```

### Vấn đề:
Không phải video nào người dùng cũng muốn lồng tiếng Việt bằng AI. Có những trường hợp cụ thể:
*   Video ngắn (Tiktok/Douyin) có âm thanh/nhạc nền gốc độc đáo, chỉ cần gắn phụ đề dịch tiếng Việt.
*   Người dùng muốn giữ nguyên giọng nói thật của người nói để đảm bảo tính tự nhiên của cảm xúc.
*   Cần xử lý video nhanh hơn, tiết kiệm chi phí gọi API tổng hợp giọng nói (TTS) vốn tốn kém nhất.
*   Chỉ cần dịch và trích xuất tệp phụ đề `.srt` phục vụ chỉnh sửa hậu kỳ thủ công.

Do đó, cần giới thiệu chế độ mới: **Subtitle-only Mode / Chỉ phụ đề**.

---

## 2. Mục tiêu mới

Chế độ chỉ gắn phụ đề sẽ chạy nhánh quy trình sau:
```text
input video/url
→ extract audio (nếu chưa có transcript, phục vụ ASR)
→ ASR (ASR nhận dạng tiếng gốc)
→ dịch thuật ngữ cảnh (Gemini/Llama)
→ validate/repair bản dịch
→ sinh transcript_vi.srt
→ (Tùy chọn) burn phụ đề vào video bằng FFmpeg
→ kết xuất subtitled_video.mp4 giữ nguyên 100% âm thanh gốc
```

### Các bước được SKIP (Bỏ qua) trong Subtitle-only mode:
*   Không chạy phân tách vocal bằng Demucs (`vocal_separator`).
*   Không chạy tổng hợp giọng nói TTS tiếng Việt (`synthesizer_vi`).
*   Không tạo thư mục phân đoạn âm thanh `segments/` và `segments_fit/`.
*   Không chạy căn chỉnh timeline audio và trộn audio (`audio_merger`).
*   Không thay thế luồng âm thanh gốc của video khi kết xuất video thành phẩm.

---

## 3. CLI options mới

Pipeline sẽ hỗ trợ cấu hình qua tham số dòng lệnh CLI:
```bash
# Chọn chế độ chạy thông qua flag --mode
python pipeline_vi.py --url "https://..." --mode subtitle_only

# Hoặc dùng flag rút gọn --subtitle-only (mặc định trỏ mode = subtitle_only)
python pipeline_vi.py --url "https://..." --subtitle-only

# Tùy chọn 1: Chỉ tạo phụ đề, không render video (--skip-video)
python pipeline_vi.py --url "https://..." --subtitle-only --skip-video

# Tùy chọn 2: Tạo phụ đề và burn phụ đề cứng vào video (--burn-subtitles)
python pipeline_vi.py --url "https://..." --subtitle-only --burn-subtitles
```

---

## 4. Tương thích với Hệ dịch thuật Ngữ cảnh

Dù chạy ở chế độ chỉ phụ đề, hệ dịch thuật nâng cấp ở task trước vẫn được giữ nguyên:
*   Vẫn sinh `video_context.json`, `glossary.json` và `character_bible.json`.
*   Vẫn validate dịch thuật bằng `translation_validator.py` và sửa đổi tự động bằng `translation_repair.py`.
*   Ưu tiên dịch từ phụ đề:
    *   Thêm trường `subtitle_vi` trỏ về bản dịch tiếng Việt dễ đọc, ngắt dòng tự nhiên.
    *   Trường `text_vi` (alias) vẫn được đồng bộ với `subtitle_vi` để duy trì tính tương thích ngược.

---

## 5. Kết xuất Video Subtitle-only

Khi kết xuất ở chế độ subtitle-only:
*   Video thành phẩm lưu với tên `subtitled_video.mp4` trong thư mục session (Không ghi đè vào `dubbed_video.mp4` của lồng tiếng).
*   FFmpeg sẽ burn phụ đề bằng bộ lọc `-vf subtitles=...` và sao chép luồng âm thanh gốc (`-c:a copy` hoặc giữ nguyên âm thanh).

---

## 6. Giao diện Web UI hỗ trợ

Cập nhật giao diện Web UI:
*   Bổ sung trường chọn **Chế độ đầu ra (Output Mode)**:
    *   *Lồng tiếng (Dub Audio)*
    *   *Chỉ phụ đề (Subtitle Only)*
*   Khi chọn *Subtitle Only*:
    *   Disable/ẩn các trường cấu hình giọng Nam/Nữ, cấu hình nhạc nền (Demucs/Duck).
    *   Bảo toàn tùy chọn "Hardsub phụ đề tiếng Việt" và "Tự động đăng bài".
*   Giao diện kết quả sẽ tự động phát video `subtitled_video.mp4` khi chạy xong chế độ phụ đề.

---

## 7. Cấu trúc tệp báo cáo `report.json`

Cập nhật trường báo cáo:
```json
{
  "mode": "subtitle_only",
  "audio_generation": "skipped",
  "tts": "skipped",
  "vocal_separation": "skipped",
  "audio_merge": "skipped",
  "subtitle_burned": true,
  "output_video": "subtitled_video.mp4"
}
```

---

## 8. Tiêu chí Nghiệm thu (Definition of Done)

*   [ ] Pipeline chạy thông suốt từ đầu đến cuối ở chế độ `--subtitle-only`.
*   [ ] Bỏ qua hoàn toàn TTS, trộn audio, tách Demucs để tiết kiệm chi phí và thời gian.
*   [ ] Bản dịch tiếng Việt được làm sạch, không còn CJK leak.
*   [ ] Video kết quả `subtitled_video.mp4` giữ nguyên 100% audio gốc và burn cứng phụ đề thành công (nếu bật `--burn-subtitles`).
*   [ ] Tệp `report.json` phản ánh chính xác trạng thái `skipped` của các khâu audio.
*   [ ] Chế độ lồng tiếng cũ (`dub_audio`) vẫn hoạt động bình thường, không bị phá vỡ.
*   [ ] Web UI được cập nhật cho phép chọn mode và hiển thị kết quả tương ứng.
*   [ ] Chạy unit tests toàn bộ dự án vượt qua thành công.
