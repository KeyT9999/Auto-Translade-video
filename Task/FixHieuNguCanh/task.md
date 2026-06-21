# Checklist thực thi: Cải tiến Hệ thống Dịch thuật Ngữ cảnh bằng AI

## Phase 0: Audit code hiện tại

*   [x] Đọc toàn bộ cấu trúc dự án.
*   [x] Tìm hiểu các file liên quan:
    *   **Pipeline chính**: [pipeline_vi.py](file:///d:/MMO/Auto-Translade-video/pipeline_vi.py) (CLI lồng tiếng Việt), [pipeline.py](file:///d:/MMO/Auto-Translade-video/pipeline.py) (CLI lồng tiếng Nhật).
    *   **Dịch thuật**: [src/translator.py](file:///d:/MMO/Auto-Translade-video/src/translator.py) (gọi Gemini/Groq Llama dịch thô).
    *   **Nhận dạng nhân vật**: [src/speaker_detector.py](file:///d:/MMO/Auto-Translade-video/src/speaker_detector.py) (gọi LLM gán speaker/gender).
    *   **Tổng hợp giọng nói**: [src/synthesizer_vi.py](file:///d:/MMO/Auto-Translade-video/src/synthesizer_vi.py) (LucyLab/LarVoice TTS cho tiếng Việt), [src/synthesizer.py](file:///d:/MMO/Auto-Translade-video/src/synthesizer.py) (Azure TTS cho tiếng Nhật).
    *   **Căn chỉnh & ghép audio**: [src/audio_merger.py](file:///d:/MMO/Auto-Translade-video/src/audio_merger.py) (co giãn thoại, chèn silence).
    *   **Giao diện web**: [web_server.py](file:///d:/MMO/Auto-Translade-video/web_server.py) (FastAPI app gọi `run_pipeline_vi`).
*   [x] Ghi chép phân tích kỹ thuật:
    *   *Dịch thuật*: Hiện tại [pipeline_vi.py](file:///d:/MMO/Auto-Translade-video/pipeline_vi.py) gọi hàm `translate_segments` của [src/translator.py](file:///d:/MMO/Auto-Translade-video/src/translator.py) truyền trực tiếp danh sách `segments` thô.
    *   *TTS*: Sử dụng `text_vi` của tệp `transcript_vi.json` làm nội dung đọc chính.
    *   *Speaker*: Hiện tại speaker được phát hiện sau bước dịch trong `pipeline_vi.py` bằng `detect_speakers(segments)` và lưu đè lại vào `transcript_vi.json`.
    *   *Cần sửa*:
        *   Tạo các module dịch thuật và tiền xử lý ngữ cảnh mới để tích hợp trước khi dịch.
        *   Nâng cấp schema của `transcript_vi.json` nhưng giữ trường `text_vi` trỏ về `dub_vi` để tương thích với giao diện Web UI và `pipeline_vi.py` hiện tại.
        *   Cập nhật `pipeline_vi.py` để sử dụng trường thoại đã qua tối ưu hóa.

---

## Phase 1: Tạo Context Builder (`src/context_builder.py`)

*   [x] Thiết lập cấu trúc sinh `video_context.json` phân tích từ `transcript_original.json`.
*   [x] Sử dụng Gemini/Groq để phân tích thông tin bối cảnh:
    *   `video_type`: Loại video (vlog, phim, drama, phóng sự...).
    *   `topic`: Chủ đề chính.
    *   `setting`: Không gian, bối cảnh diễn ra.
    *   `speaker_style`: Phong cách ngôn ngữ của người nói.
    *   `narration_pov`: Góc nhìn kể chuyện (ngôi thứ nhất, thứ ba...).
    *   `tone`: Giọng điệu (hài hước, trang nghiêm, giận dữ...).
    *   `translation_style`: Văn phong dịch tương ứng.
    *   `entities`: Các thực thể/địa danh quan trọng.
    *   `deixis_policy`: Quy tắc dịch từ chỉ vị trí (như `这里`, `这边`, `楼上`, `下面`).
    *   `pronoun_policy`: Gợi ý xưng hô tương ứng.
*   [x] Xây dựng cơ chế fallback an toàn (sinh context trống/mặc định) nếu AI bị lỗi.

---

## Phase 2: Tạo Glossary Builder (`src/glossary_builder.py`)

*   [x] Viết mã sinh `glossary.json` tự động từ transcript gốc và bối cảnh video.
*   [x] Tự động lọc các từ chỉ vị trí (deixis) tiếng Trung và đề xuất bản dịch tương ứng.
*   [x] Tạo cơ chế fallback nạp bản glossary mặc định cho tiếng Trung/Nhật/Anh.
*   [x] Cho phép truyền glossary này vào prompt của Translator.

---

## Phase 3: Tạo Character/Speaker Profiler (`src/character_profiler.py`)

*   [x] Viết mã phân tích transcript để sinh hồ sơ nhân vật `character_bible.json`.
*   [x] Với video vlog (một người nói): Gán vai trò người kể chuyện (Narrator) với xưng hô "mình" - "mọi người".
*   [x] Với phim truyền hình/drama: Phát hiện danh sách nhân vật, ước tính độ tuổi, giới tính và đề xuất các đại từ xưng hô phù hợp (tôi-bạn, anh-em, mẹ-con, tớ-cậu...).
*   [x] Định nghĩa cấu trúc `characters` và `global_pronoun_rules` làm đầu vào cho Translator.

---

## Phase 4: Nâng cấp Translator thành Context-aware Translator (`src/contextual_translator.py`)

*   [x] Xây dựng cấu trúc dịch cửa sổ trượt (sliding window):
    *   Mỗi window chứa 8-12 segments mục tiêu (target segments).
    *   Kèm theo 2-3 segments ngữ cảnh phía trước (previous context) và 2-3 segments ngữ cảnh phía sau (next context).
*   [x] Thiết kế prompt dịch thuật mới tích hợp: `video_context`, `glossary`, `character_bible` và các đoạn ngữ cảnh trượt.
*   [x] Gọi Gemini và Groq Llama fallback để dịch, yêu cầu đầu ra JSON chuẩn xác.
*   [x] Schema kết quả trả về của mỗi segment bao gồm: `id`, `source_text`, `literal_vi`, `dub_vi`, `speaker`, `speaker_gender`, `pronoun_note`, `context_note`, `risk_flags`.

---

## Phase 5: Tạo Translation Validator (`src/translation_validator.py`)

*   [x] Viết module kiểm tra chất lượng tự động sau khi dịch.
*   [x] Sử dụng regex `[\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf]` để phát hiện rò rỉ ký tự CJK.
*   [x] Kiểm tra các lỗi dịch ngượng từ chỉ vị trí và rò rỉ ngôn ngữ gốc.
*   [x] Đánh giá độ dài câu thoại (`dub_vi`) so với duration của segment (cành báo nếu tốc độ nói vượt quá 15 ký tự/giây).
*   [x] Phát hiện lỗi đồng loạt giới tính/nhân vật (Ví dụ: toàn bộ nhân vật bị gán `neutral`).
*   [x] Xuất kết quả đánh giá chất lượng ra tệp `translation_quality_report.json`.

---

## Phase 6: Tạo Translation Repair (`src/translation_repair.py`)

*   [x] Xây dựng module tự động sửa lỗi cho các segment bị đánh giá không đạt (bad segments).
*   [x] Trích xuất các segment bị validator đánh dấu lỗi, gửi yêu cầu sửa đổi riêng lẻ lên AI kèm chỉ dẫn cụ thể (ví dụ: "Loại bỏ ký tự Trung Quốc", "Rút ngắn độ dài câu",...).
*   [x] Bảo toàn tuyệt đối ID thoại, thời gian thoại của các segment được sửa.
*   [x] Ghi nhận lịch sử sửa lỗi vào tệp `translation_repair_report.json`.
*   [x] Chạy lại validator sau khi sửa lỗi để kiểm chứng. Nếu lỗi nặng không sửa được, phát thông báo dừng pipeline.

---

## Phase 7: Tạo Timeline-aware Rewrite (`src/timeline_rewriter.py`)

*   [x] Tạo module tinh chỉnh độ dài câu thoại trước khi đưa sang TTS.
*   [x] Dựa vào duration của từng segment:
    *   Rút gọn từ ngữ của `dub_vi` nếu câu quá dài so với duration để tránh nói quá nhanh.
    *   Bổ sung từ đệm biểu cảm tự nhiên (nhé, nha, nhé mọi người...) nếu câu quá ngắn so với duration để tránh khoảng lặng ngắt quãng lớn.
*   [x] Lưu trữ bản ghi nhận tối ưu hóa vào các trường `timing_rewrite_applied`, `original_dub_vi`, `final_dub_vi`.

---

## Phase 8: Tích hợp vào Pipeline tiếng Việt (`pipeline_vi.py`)

*   [x] Cập nhật thứ tự thực thi trong `pipeline_vi.py`:
    *   Tích hợp khâu Context Builder, Glossary Builder, Character Profiler ngay sau khi có `transcript_original.json`.
    *   Thay thế module `translator.py` cũ bằng `contextual_translator.py` mới.
    *   Tích hợp khâu Validation, Repair và Timeline-aware rewriter.
*   [x] Ghi nhận toàn bộ các tệp báo cáo JSON mới vào thư mục session output.
*   [x] Cập nhật module TTS và audio merger để sử dụng trường dữ liệu thoại đã tối ưu (`final_dub_vi` hoặc `dub_vi`), duy trì tương thích ngược qua alias `text_vi`.

---

## Phase 9: Viết Test & Công cụ kiểm chứng

*   [x] Tạo các unit tests trong `tests/` để phủ sóng validator, schema, và cơ chế repair.
*   [x] Viết script công cụ [tools/check_translation_quality.py](file:///d:/MMO/Auto-Translade-video/tools/check_translation_quality.py) để người dùng có thể kiểm tra nhanh chất lượng dịch thuật của một session bất kỳ từ dòng lệnh.

---

## Phase 10: Vận hành thực tế & Đánh giá chất lượng

*   [x] Chạy syntax check và toàn bộ unit tests bằng pytest.
*   [x] Chạy thử nghiệm thực tế với một video tiếng Trung (hoặc video demo) để kiểm tra:
    *   Độ mượt mà của lời thoại tiếng Việt.
    *   Sự biến mất hoàn toàn của CJK leak.
    *   Sự xuất hiện đầy đủ của các tệp tin báo cáo phụ trợ.
    *   Pipeline chạy ổn định end-to-end không bị gián đoạn.
