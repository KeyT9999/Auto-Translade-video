# Yêu cầu cải tiến Hệ thống Dịch thuật Ngữ cảnh bằng AI

## 1. Bối cảnh hiện tại

Pipeline hiện tại của dự án:
```text
download/input video
→ extract audio
→ ASR/transcript_original
→ translate/transcript_vi
→ speaker detection nếu có
→ TTS
→ fit timeline
→ audio merge
→ render video
```

### Vấn đề hiện tại:
*   Đầu ra của ASR chia thành các phân đoạn (segments) quá ngắn.
*   Hệ thống dịch thuật cũ gọi API dịch từng segment riêng lẻ và cô lập. Do thiếu đi thông tin ngữ cảnh toàn cục (video topic, quan hệ nhân vật, không gian địa lý, các câu nói trước sau), bản dịch tiếng Việt (`text_vi`) thường bị rời rạc, cứng nhắc, mang văn phong dịch máy.
*   Bản dịch thường xuyên bị lọt ký tự gốc tiếng Trung/Nhật/Hàn (CJK leak) do AI dịch bị ảnh hưởng bởi prompt hoặc source text (Ví dụ lỗi: `坐 thang máy`).
*   Các từ chỉ vị trí tiếng Trung như `这里` (ở đây), `这边` (bên này), `楼上` (tầng trên), `下面` (bên dưới/phía dưới) hay bị dịch ngượng hoặc sai ngữ cảnh (ví dụ: "Đâu cũng có thể ngồi" thay vì "Chỗ này cũng ngồi được").
*   Quy trình gán giọng (speaker/gender) trung tính, chưa phân tích đầy đủ hội thoại để gán xưng hô nhất quán.
*   Chưa tối ưu hóa bản dịch lồng tiếng theo độ dài phát âm của segment (duration/timeline), gây ra việc nói quá nhanh/chồng chéo ở khâu TTS.
*   Pipeline chưa có cơ chế kiểm tra chất lượng bản dịch (validate) và tự động sửa lỗi (repair) trước khi chuyển sang TTS/render, dễ làm phát sinh lỗi nghiêm trọng ở sản phẩm cuối.

---

## 2. Các vấn đề cần giải quyết (Vấn đề cần fix)

1.  **Dịch thiếu ngữ cảnh**: Thiếu một hồ sơ mô tả bối cảnh chung của video (`video_context.json`).
2.  **Từ vựng & Địa danh không nhất quán**: Thiếu bảng thuật ngữ glossary chuẩn hóa (`glossary.json`) để hướng dẫn AI xử lý các từ chỉ vị trí và các thực thể đặc trưng trong video.
3.  **Xưng hô không tự nhiên/Nhân vật không rõ ràng**: Thiếu hồ sơ nhân vật (`character_bible.json`) lưu giữ tính cách, giới tính và đại từ xưng hô tương ứng của từng speaker.
4.  **Dịch cô lập**: Cần chuyển đổi sang phương pháp dịch theo cửa sổ trượt (sliding window) thay vì dịch từng segment riêng rẽ.
5.  **Chưa tách biệt vai trò bản dịch**: Không phân biệt giữa dịch nghĩa chính xác (literal translation) và dịch lời thoại lồng tiếng (dubbing translation) để TTS đọc tự nhiên.
6.  **Thiếu Validator**: Không có cơ chế tự động phát hiện CJK leak, segment rỗng, từ ngượng, hoặc câu dịch quá dài so với duration.
7.  **Thiếu Auto-Repair**: Không tự động phát hiện và gửi segment lỗi lên AI để sửa chữa (repair) riêng lẻ.
8.  **Chưa tối ưu thời gian**: Bản dịch dubbing chưa được điều chỉnh độ dài từ ngữ phù hợp timeline segment trước khi chuyển sang TTS.

---

## 3. Mục tiêu kỹ thuật & Kiến trúc mới

Hệ thống dịch thuật ngữ cảnh mới sẽ có kiến trúc như sau:

```text
transcript_original.json
→ context_builder (sinh video_context.json)
→ character_profiler (sinh character_bible.json)
→ glossary_builder (sinh glossary.json)
→ contextual_translator (dịch sliding window)
  → transcript_vi.json (mở rộng schema chứa literal_vi + dub_vi)
→ translation_validator (sinh translation_quality_report.json)
→ translation_repair (sửa các segment lỗi, sinh translation_repair_report.json)
→ timeline_rewriter (tối ưu độ dài dub_vi theo duration thực)
→ TTS (sử dụng dub_vi đã tối ưu)
```

---

## 4. Đặc tả Output Artifact mới

Thư mục output của mỗi session sẽ sinh ra thêm hoặc chuẩn hóa các tệp tin sau:
*   `video_context.json`: Chứa bối cảnh, thể loại, văn phong, để lại deixis policy của video.
*   `character_bible.json`: Hồ sơ các nhân vật xuất hiện, giới tính, đại từ xưng hô tương ứng.
*   `glossary.json`: Bản đồ thuật ngữ, deixis policy xử lý từ chỉ vị trí.
*   `translation_quality_report.json`: Kết quả validate bản dịch (danh sách lỗi nghiêm trọng/nhẹ).
*   `translation_repair_report.json`: Nhật ký sửa đổi các segment lỗi bằng AI.

### Mở rộng schema của `transcript_vi.json`:
Mỗi segment trong tệp JSON đầu ra dịch thuật cần có cấu trúc:
```json
{
  "id": 1,
  "text": "source text",
  "start": 0.0,
  "end": 2.0,
  "duration": 2.0,
  "literal_vi": "bản dịch nghĩa chính xác từng từ/câu",
  "dub_vi": "bản lời thoại tiếng Việt tối ưu cho TTS (lồng tiếng)",
  "text_vi": "alias tương thích cũ, lấy giá trị của dub_vi",
  "speaker": "SPEAKER_00 hoặc tên nhân vật cụ thể",
  "speaker_gender": "male/female/neutral/unknown",
  "context_note": "ghi chú bối cảnh phân đoạn",
  "pronoun_note": "ghi chú đại từ xưng hô áp dụng",
  "risk_flags": []
}
```

---

## 5. Quy tắc Dịch thuật Mới (Lồng tiếng tự nhiên)

*   **Độ tự nhiên được ưu tiên**: Dịch thoát ý theo phong cách hội thoại nói (văn nói), không dịch cứng nhắc từ-qua-từ.
*   **Không rò rỉ CJK**: Cấm tuyệt đối việc để lọt ký tự Trung, Nhật, Hàn, hoặc các từ dịch nửa vời trong `text_vi`/`dub_vi`.
*   **Xử lý deixis (vị trí)**: Thay thế các câu dịch vụng bằng các cụm tự nhiên ("chỗ này", "ở đây", "phía bên kia", "tầng trên",...).
*   **Xưng hô thống nhất**: Sử dụng thông tin trong `character_bible.json` để chọn cặp xưng hô thích hợp (Tôi-bạn, tớ-cậu, anh-em, mẹ-con,...) xuyên suốt toàn bộ video.
*   **Phù hợp với Timeline**: Tốc độ nói tiếng Việt cần kiểm soát ở mức ~12 ký tự/giây (bình thường), tối đa ~15 ký tự/giây. Rút gọn câu thoại nếu duration quá ngắn; bù thêm từ đệm ("nhỉ", "nhé", "nào",...) nếu thoại quá ngắn so với duration mà không bịa nội dung.

---

## 6. Tiêu chuẩn Validator & Tự động sửa lỗi (Repair)

Validator sẽ chạy kiểm tra sau khi dịch xong:
1.  **CJK Leak**: Sử dụng regex `[\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf]` để phát hiện ký tự Trung/Nhật/Hàn.
2.  **Từ ngượng**: Phát hiện các chuỗi từ cấm như "Đâu cũng có thể ngồi", "Đâu nhìn rõ", "Đâu là trong nhà",...
3.  **Timeline Overflow**: Phát hiện các segment có tỷ lệ ký tự/giây vượt quá 15 ký tự/giây.
4.  **Speaker Neutrality**: Cảnh báo nếu toàn bộ video có nhiều người nói nhưng tất cả đều bị gán `neutral`.

### Quy tắc xử lý:
*   *Lỗi nhẹ (Ví dụ: câu hơi dài, lọt vài từ ngượng)*: Gửi lên module **Translation Repair** để AI sửa chữa riêng lẻ các segment lỗi, giữ nguyên ID thoại.
*   *Lỗi nặng (Ví dụ: dịch lỗi JSON, CJK leak nghiêm trọng không sửa được)*: Dừng pipeline trước khâu TTS, báo cáo lỗi chi tiết ra file report.

---

## 7. Khả năng Tương thích ngược (Backward Compatibility)

*   Nếu hệ thống dịch thuật mới gặp sự cố mạng hoặc lỗi API không thể khắc phục, hệ thống phải tự động **fallback** về module dịch cũ (`src/translator.py`) hoặc báo cáo lỗi cụ thể mà không làm crash đột ngột toàn bộ tiến trình.
*   Các tệp tin đầu ra truyền thống như `transcript_vi.json` (chứa alias `text_vi`), `transcript_vi.srt` vẫn phải được ghi nhận và sinh ra đầy đủ ở định dạng chuẩn.

---

## 8. Tiêu chí Nghiệm thu (Definition of Done)

*   [ ] Có đầy đủ tài liệu `requirement.md` và `task.md` trong thư mục task.
*   [ ] Pipeline hoạt động trơn tru từ đầu đến cuối không lỗi cú pháp hay crash.
*   [ ] Sinh đầy đủ các file phụ trợ bối cảnh: `video_context.json`, `character_bible.json`, `glossary.json` trước khi thực hiện dịch thuật.
*   [ ] Bản dịch được thực hiện qua cơ chế cửa sổ trượt (sliding window) kết hợp thông tin bối cảnh.
*   [ ] File `transcript_vi.json` tuân thủ đúng schema mở rộng (`literal_vi`, `dub_vi`, `text_vi`).
*   [ ] Bản dịch sạch 100% CJK leak, dịch tự nhiên các cụm từ chỉ địa điểm/vị trí.
*   [ ] Validator chạy thành công và tạo tệp báo cáo `translation_quality_report.json`.
*   [ ] Tự động repair các segment không đạt yêu cầu và ghi lại trong `translation_repair_report.json`.
*   [ ] TTS lồng tiếng sử dụng đúng trường dữ liệu `dub_vi` (hoặc `final_dub_vi`) đã qua tinh chỉnh thời lượng.
*   [ ] Có kiểm thử tự động (unit tests) hoặc script công cụ kiểm tra chất lượng bản dịch.
