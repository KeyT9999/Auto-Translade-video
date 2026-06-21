# Checklist thực thi: Phát triển Chế độ Chỉ phụ đề (Subtitle-only Mode)

## Phase 0: Audit code hiện tại

*   [x] Tìm pipeline tiếng Việt chính: [pipeline_vi.py](file:///d:/MMO/Auto-Translade-video/pipeline_vi.py).
*   [x] Tìm module render: [src/video_merger.py](file:///d:/MMO/Auto-Translade-video/src/video_merger.py).
*   [x] Tìm Web UI: [web_server.py](file:///d:/MMO/Auto-Translade-video/web_server.py) và [static/index.html](file:///d:/MMO/Auto-Translade-video/static/index.html).
*   [x] Phân tích skip logic:
    *   Trong `subtitle_only` mode, cần bỏ qua:
        *   Tách vocal Demucs (Step 2.5).
        *   Tổng hợp TTS (Step 5).
        *   Căn chỉnh timeline audio & Merge audio (Step 6).
    *   Tệp video đầu ra khi burn sub sẽ là `subtitled_video.mp4` giữ nguyên audio gốc, thay vì `dubbed_video.mp4` dùng audio lồng tiếng Việt.

---

## Phase 1: Cấu hình tham số dòng lệnh CLI và API Schema

*   [x] Cập nhật `parse_args` trong `pipeline_vi.py`:
    *   Thêm `--mode` (nhận `dub_audio` hoặc `subtitle_only`, mặc định `dub_audio`).
    *   Thêm `--subtitle-only` (nếu bật, gán `mode = "subtitle_only"`).
*   [x] Cập nhật API schema `PipelineRequest` trong `web_server.py` để nhận trường `mode` (mặc định `"dub_audio"`).

---

## Phase 2: Phân nhánh xử lý Pipeline theo Mode trong `pipeline_vi.py`

*   [x] Trong `run_pipeline_vi(...)`:
    *   Đọc tham số `mode` truyền vào.
    *   Nếu `mode == "subtitle_only"`:
        *   Bỏ qua chạy Demucs/tách âm thanh nền ở Step 2.5.
        *   Tiến hành dịch thuật và tối ưu hóa bình thường (Step 4).
        *   Bỏ qua Step 5 (TTS), Step 6 (Fit timeline & Merge audio).
        *   Thiết lập luồng render video với phụ đề và giữ nguyên audio gốc ở Step 7.
*   [x] Cập nhật việc tạo báo cáo `report.json` phản ánh trạng thái `skipped` cho các bước liên quan đến audio.

---

## Phase 3: Nâng cấp Video Merger hỗ trợ ghi phụ đề giữ audio gốc

*   [x] Tạo hoặc nâng cấp hàm render trong `src/video_merger.py`:
    *   Thêm hàm `burn_subtitles_to_video(video_path, srt_path, output_path)` sử dụng FFmpeg để ghi phụ đề cứng lên video gốc và sao chép trực tiếp kênh âm thanh gốc (`-c:a copy` hoặc `-c:a aac`).

---

## Phase 4: Thiết lập Phụ đề dễ đọc (Subtitle Formatter)

*   [x] Thêm module hoặc hàm định dạng phụ đề `src/subtitle_formatter.py` để làm sạch phụ đề trước khi burn (ví dụ: tự động xuống dòng nếu câu quá dài, giới hạn độ rộng dòng).
*   [x] Tích hợp định dạng phụ đề vào SRT generator.

---

## Phase 5: Nâng cấp Web UI hỗ trợ chọn Chế độ đầu ra

*   [x] Cập nhật [static/index.html](file:///d:/MMO/Auto-Translade-video/static/index.html):
    *   Thêm mục chọn "Chế độ đầu ra" (Lồng tiếng / Chỉ phụ đề).
    *   Sử dụng JavaScript để ẩn/hiện hoặc disable các tùy chọn liên quan tới TTS và tách nhạc nền (Demucs) khi người dùng chọn chế độ chỉ phụ đề.
    *   Truyền tham số `mode` lên API `/api/run`.
    *   Hiển thị đúng video `subtitled_video.mp4` trong khung phát trực tiếp của giao diện khi hoàn thành.
*   [x] Cập nhật endpoint `/api/run` trong [web_server.py](file:///d:/MMO/Auto-Translade-video/web_server.py) để chuyển tiếp tham số `mode` vào pipeline chính.

---

## Phase 6: Cập nhật Resume Logic cho Subtitle-only Mode

*   [x] Tinh chỉnh resume logic trong `pipeline_vi.py` để tránh báo lỗi thiếu các tệp audio/TTS khi chạy resume một session ở chế độ chỉ phụ đề.

---

## Phase 7: Viết Test & Vận hành kiểm chứng

*   [x] Viết unit tests kiểm tra:
    *   CLI parsing nhận dạng đúng mode.
    *   Mặc định vẫn chạy chế độ lồng tiếng.
    *   Chế độ chỉ phụ đề bỏ qua các bước xử lý audio.
    *   Kết xuất video phụ đề cứng giữ đúng âm thanh gốc.
*   [x] Chạy unit tests toàn bộ dự án để đảm bảo tính ổn định và tương thích.
