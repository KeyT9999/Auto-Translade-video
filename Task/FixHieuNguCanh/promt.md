# SUPER PROMPT CHO ANTIGRAVITY

Bạn hãy đọc toàn bộ dự án Auto-Translade-video hiện tại trước khi sửa code.

Mục tiêu của task này là **cải tiến hệ thống dịch thuật ngữ cảnh bằng AI** trong pipeline lồng tiếng video, đặc biệt là các lỗi:

* AI dịch từng segment quá rời rạc, không hiểu toàn cảnh video.
* AI không hiểu nhân vật, speaker, vai trò, xưng hô.
* Bản dịch tiếng Việt còn lọt ký tự tiếng Trung/Nhật/Hàn, ví dụ lỗi kiểu `坐 thang máy`.
* Các từ chỉ vị trí trong tiếng Trung như `这里`, `这边`, `楼上`, `下面` bị dịch sai/ngượng, ví dụ “Đâu cũng có thể ngồi”, “Đâu nhìn rõ”, “Đâu là trong nhà”.
* Bản dịch chưa phù hợp để lồng tiếng/TTS vì chưa tối ưu theo timeline, duration, độ dài câu đọc.
* Speaker detection hiện tại gần như chưa có tác dụng vì nhiều đoạn bị gán chung một speaker/gender trung tính.
* Pipeline chưa có bước kiểm tra chất lượng hậu dịch trước khi đưa sang TTS/render.

## YÊU CẦU BẮT BUỘC TRƯỚC KHI CODE

Không được sửa code ngay.

Trước tiên hãy tạo hoặc cập nhật các file tài liệu sau:

1. `requirement.md`
2. `task.md`

Nếu trong dự án đã có thư mục chuyên chứa task/docs thì đặt file vào đúng thư mục đó. Nếu chưa có thì tạo ở thư mục phù hợp, ví dụ:

```text
Task/context_translation_fix/requirement.md
Task/context_translation_fix/task.md
```

Sau khi tạo 2 file này, mới bắt đầu implement theo task.

## PHẦN 1: NỘI DUNG CẦN CÓ TRONG requirement.md

Hãy viết `requirement.md` theo góc nhìn toàn cảnh hệ thống.

Nội dung bắt buộc gồm:

### 1. Bối cảnh hiện tại

Mô tả pipeline hiện tại của dự án:

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

Chỉ rõ vấn đề hiện tại nằm ở khâu:

```text
ASR output segment quá ngắn
→ dịch từng segment thiếu ngữ cảnh
→ text_vi không tự nhiên
→ có lỗi lọt ngôn ngữ gốc
→ TTS đọc lỗi
→ video đầu ra thiếu tự nhiên
```

### 2. Vấn đề cần fix

Liệt kê rõ các lỗi cần xử lý:

* Dịch thiếu ngữ cảnh toàn video.
* Không có bước tạo `video_context.json`.
* Không có hoặc chưa chuẩn hóa `glossary.json`.
* Không có `character_bible.json`/speaker profile đủ mạnh.
* Không có rule dịch nhất quán cho đại từ/xưng hô.
* Không có policy cho từ chỉ vị trí như `这里`, `这边`, `楼上`, `下面`.
* Không có bước dịch theo cụm/sliding window.
* Không phân biệt bản dịch nghĩa và bản lời thoại dùng cho TTS.
* Không có bước validate hậu dịch trước TTS.
* Không có bước repair tự động cho segment lỗi.
* Không tối ưu bản dịch theo duration/timeline trước khi TTS.

### 3. Mục tiêu kỹ thuật

Cần cải tiến pipeline dịch thành kiến trúc mới:

```text
transcript_original.json
→ context_builder
→ video_context.json
→ speaker/character profiler
→ character_bible.json
→ glossary/pronoun map
→ glossary.json
→ context-aware translation bằng sliding window
→ transcript_vi.json gồm literal_vi + dub_vi
→ translation validator
→ repair bad segments
→ timeline-aware rewrite
→ TTS dùng dub_vi
```

### 4. Output artifact mới

Sau khi chạy pipeline, output directory cần có thêm hoặc chuẩn hóa các file:

```text
video_context.json
character_bible.json
glossary.json
translation_quality_report.json
translation_repair_report.json
```

`transcript_vi.json` cần mở rộng schema để hỗ trợ:

```json
{
  "id": 1,
  "text": "source text",
  "start": 0.0,
  "end": 2.0,
  "duration": 2.0,
  "literal_vi": "bản dịch nghĩa chính xác",
  "dub_vi": "bản lời thoại tiếng Việt dùng cho TTS",
  "text_vi": "alias tương thích cũ, ưu tiên bằng dub_vi",
  "speaker": "SPEAKER_00 hoặc NV_CHINH",
  "speaker_gender": "male/female/neutral/unknown",
  "context_note": "ghi chú ngữ cảnh nếu có",
  "pronoun_note": "ghi chú xưng hô nếu có",
  "risk_flags": []
}
```

### 5. Quy tắc dịch mới

Dịch thuật phải tuân thủ:

* Không dịch từng chữ máy móc.
* Ưu tiên tiếng Việt tự nhiên khi lồng tiếng.
* Không để sót ký tự Trung/Nhật/Hàn trong `text_vi`/`dub_vi`.
* Không dùng các câu ngượng như “Đâu cũng có thể ngồi” nếu ngữ cảnh là “ở đây/chỗ này”.
* Với video vlog: ưu tiên “mình”, “mọi người”, “ở đây”, “chỗ này”, “phía này”.
* Với phim/drama: dùng xưng hô theo `character_bible.json`.
* Giữ đúng ý, không thêm thông tin sai.
* Câu dùng cho TTS phải phù hợp duration.
* Nếu `dub_vi` quá dài thì rewrite ngắn hơn.
* Nếu `dub_vi` quá ngắn so với cảnh, có thể thêm từ đệm tự nhiên nhưng không bịa nội dung.

### 6. Validator bắt buộc

Cần có module validator kiểm tra:

* Còn ký tự CJK trong tiếng Việt.
* Còn text source-language bị lọt.
* `dub_vi` rỗng hoặc quá ngắn bất thường.
* `dub_vi` quá dài so với duration.
* Các từ dịch sai/ngượng theo rule, ví dụ:

  * “Đâu cũng có thể ngồi”
  * “Đâu nhìn rõ”
  * “Đâu là trong nhà”
  * “Cạnh này” dùng sai ngữ cảnh
* Xưng hô không nhất quán.
* Speaker/gender bị `neutral` toàn bộ trong video có nhiều người nói.
* JSON output từ AI lỗi format.

Nếu lỗi nhẹ thì tự repair segment lỗi.
Nếu lỗi nghiêm trọng thì fail rõ ràng, ghi report, không đưa sang TTS/render.

### 7. Backward compatibility

Không được phá pipeline hiện tại.

Nếu module mới lỗi, cần có fallback an toàn:

```text
fallback sang translator cũ
hoặc tạo report lỗi rõ ràng
không làm crash toàn bộ pipeline nếu có thể recover
```

Các file cũ như:

```text
transcript_original.json
transcript_vi.json
transcript_vi.srt
timing_guide.json
fit_adjustments.json
```

vẫn phải được tạo đúng.

### 8. Tiêu chí nghiệm thu

Task được coi là hoàn thành khi:

* Pipeline vẫn chạy end-to-end.
* `video_context.json` được tạo trước khi dịch.
* `glossary.json` được tạo hoặc fallback mặc định.
* `character_bible.json` được tạo.
* Dịch theo cụm/sliding window thay vì từng segment cô lập.
* `transcript_vi.json` có `literal_vi`, `dub_vi`, `text_vi`.
* `text_vi`/`dub_vi` không còn ký tự Trung/Nhật/Hàn.
* Có `translation_quality_report.json`.
* Các segment lỗi được repair trước TTS.
* TTS dùng `dub_vi` thay vì bản dịch thô.
* Có test hoặc script kiểm chứng tối thiểu cho validator và schema.

---

## PHẦN 2: NỘI DUNG CẦN CÓ TRONG task.md

Hãy viết `task.md` thành checklist thực thi rõ ràng theo thứ tự sau.

### Phase 0: Audit code hiện tại

* Đọc toàn bộ cấu trúc project.
* Tìm các file liên quan:

  * pipeline chính tiếng Việt.
  * translator module.
  * speaker detector module.
  * synthesizer/TTS module.
  * audio merger/timing fit module.
  * SRT generator.
  * web server nếu có gọi pipeline.
* Ghi lại trong `task.md`:

  * file nào đang dịch.
  * file nào đang tạo `transcript_vi.json`.
  * file nào đang gọi TTS.
  * field nào đang được TTS sử dụng.
  * chỗ nào cần sửa để không phá compatibility.

### Phase 1: Tạo Context Builder

Tạo module mới, ví dụ:

```text
src/context_builder.py
```

Chức năng:

* Nhận `transcript_original.json`.
* Đọc toàn bộ transcript.
* Gọi AI để sinh `video_context.json`.
* Nếu AI lỗi thì tạo fallback context đơn giản.
* Context cần có:

  * video_type
  * topic
  * setting
  * speaker_style
  * narration_pov
  * tone
  * translation_style
  * entities
  * deixis_policy
  * pronoun_policy

Ví dụ `deixis_policy`:

```json
{
  "这里": "ở đây / chỗ này",
  "这边": "phía này / khu này / bên này",
  "楼上": "tầng trên / phía trên",
  "下面": "bên dưới / tầng dưới"
}
```

### Phase 2: Tạo Glossary Builder

Tạo module mới, ví dụ:

```text
src/glossary_builder.py
```

Chức năng:

* Sinh `glossary.json` từ transcript + context.
* Chuẩn hóa entity/từ khóa.
* Với video tiếng Trung, cần nhận diện các cụm như:

  * 楼
  * 咖啡厅
  * 前台
  * 电梯
  * 这里
  * 这边
  * 楼上
  * 下面
* Glossary phải được truyền vào prompt dịch.

### Phase 3: Tạo Character/Speaker Profiler

Tạo hoặc nâng cấp:

```text
src/speaker_detector.py
```

hoặc tạo module riêng:

```text
src/character_profiler.py
```

Chức năng:

* Sinh `character_bible.json`.
* Với video một người nói/vlog: tạo narrator profile.
* Với video nhiều speaker: gom speaker theo audio diarization nếu có, hoặc theo transcript/context nếu chưa có diarization.
* Output tối thiểu:

```json
{
  "characters": [
    {
      "speaker_id": "SPEAKER_00",
      "role": "narrator",
      "gender": "unknown",
      "age": "unknown",
      "personality": "tự nhiên",
      "vi_pronoun_self": "mình",
      "vi_pronoun_other": "mọi người",
      "voice_id": null
    }
  ],
  "global_pronoun_rules": {
    "我们": "mình / chúng mình",
    "你": "bạn / mọi người",
    "他": "nhân viên / người đó / anh ấy tùy ngữ cảnh"
  }
}
```

### Phase 4: Nâng cấp Translator thành Context-aware Translator

Sửa module dịch hiện tại hoặc tạo module mới:

```text
src/contextual_translator.py
```

Yêu cầu:

* Không dịch từng segment cô lập.
* Dịch theo sliding window:

  * target window: 8–12 segments.
  * previous context: 2–3 segments.
  * next context: 2–3 segments.
* AI chỉ được trả kết quả cho target segments.
* Prompt phải nhận:

  * video_context
  * glossary
  * character_bible
  * previous_segments
  * target_segments
  * next_segments
* Output phải là JSON hợp lệ.
* Mỗi segment trả:

  * id
  * source_text
  * literal_vi
  * dub_vi
  * speaker
  * speaker_gender
  * pronoun_note
  * context_note
  * risk_flags

### Phase 5: Translation Validator

Tạo module:

```text
src/translation_validator.py
```

Chức năng:

* Validate `transcript_vi.json` trước khi TTS.
* Check CJK bằng regex:

```python
import re
CJK_RE = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf]')
```

* Check rỗng/null.
* Check quá dài/quá ngắn theo duration.
* Check JSON schema.
* Check các phrase tiếng Việt ngượng/sai rule.
* Ghi `translation_quality_report.json`.

Report format:

```json
{
  "total_segments": 36,
  "valid_segments": 34,
  "bad_segments": 2,
  "issues": [
    {
      "id": 6,
      "field": "dub_vi",
      "severity": "error",
      "type": "SOURCE_LANGUAGE_LEAK",
      "message": "Vietnamese text still contains CJK characters",
      "text": "Họ sẽ dẫn chúng ta vào đây坐 thang máy"
    }
  ]
}
```

### Phase 6: Translation Repair

Tạo module:

```text
src/translation_repair.py
```

Chức năng:

* Nhận danh sách bad segments từ validator.
* Gửi lại AI repair chỉ các segment lỗi.
* Không thay đổi id/start/end/duration.
* Không thay đổi segment không lỗi.
* Không được trả ký tự source-language.
* Ghi `translation_repair_report.json`.
* Sau repair, chạy validator lại.
* Nếu vẫn còn lỗi nghiêm trọng, stop trước TTS và báo rõ.

### Phase 7: Timeline-aware Rewrite

Tạo hoặc nâng cấp logic trước TTS:

```text
src/timeline_rewriter.py
```

Chức năng:

* Dùng duration từng segment để tối ưu `dub_vi`.
* Nếu câu quá dài so với duration, rewrite ngắn hơn.
* Nếu câu quá ngắn nhưng scene còn dài, có thể thêm từ tự nhiên vừa đủ, không bịa thông tin.
* Không chỉ phụ thuộc vào speed-up audio.
* Ghi chú vào field:

  * `timing_rewrite_applied`
  * `original_dub_vi`
  * `final_dub_vi`

Ví dụ:

```json
{
  "id": 18,
  "source": "75楼到了",
  "duration": 1.06,
  "old_dub_vi": "Đã đến tầng 75",
  "new_dub_vi": "Tầng 75 rồi."
}
```

### Phase 8: Tích hợp vào Pipeline

Tích hợp thứ tự mới vào pipeline tiếng Việt:

```text
ASR/transcript_original.json
→ context_builder
→ glossary_builder
→ character_profiler
→ contextual_translator
→ translation_validator
→ translation_repair nếu cần
→ timeline_rewriter
→ tạo transcript_vi.json/transcript_vi.srt
→ TTS dùng dub_vi/final_dub_vi
→ audio fit/merge
→ render
```

Quan trọng:

* TTS không dùng bản dịch thô nếu đã có `dub_vi` hoặc `final_dub_vi`.
* `text_vi` vẫn được giữ để tương thích, nhưng nên map từ `final_dub_vi` hoặc `dub_vi`.

Priority field:

```text
final_dub_vi > dub_vi > text_vi > literal_vi
```

### Phase 9: Test và kiểm chứng

Tạo hoặc cập nhật test:

* Test validator bắt CJK leak.
* Test validator bắt `dub_vi` rỗng.
* Test schema `transcript_vi.json`.
* Test repair không đổi id/start/end.
* Test translator output parse JSON.
* Test fallback khi AI lỗi.
* Test TTS chọn đúng field `final_dub_vi/dub_vi`.

Nếu dự án chưa có test framework đầy đủ, tạo script kiểm tra tối thiểu:

```text
tools/check_translation_quality.py
```

Script này nhận đường dẫn output session và in report:

```bash
python tools/check_translation_quality.py output/VN/<session_id>
```

### Phase 10: Chạy kiểm thử thực tế

Sau khi code xong:

* Chạy syntax check.
* Chạy unit tests nếu có.
* Chạy thử với một transcript mẫu.
* Kiểm tra output không còn CJK trong bản tiếng Việt.
* Kiểm tra `translation_quality_report.json`.
* Kiểm tra `transcript_vi.srt`.
* Kiểm tra pipeline không bị crash.

---

## PROMPT AI DỊCH MẪU CẦN ÁP DỤNG

Hãy tạo prompt dịch mới theo tinh thần sau, có thể đặt trong code dưới dạng template:

```text
Bạn là biên dịch viên chuyên lồng tiếng video sang tiếng Việt.

Nhiệm vụ:
- Dịch từ {source_language} sang tiếng Việt tự nhiên.
- Không dịch từng chữ.
- Ưu tiên câu nói nghe tự nhiên khi TTS/lồng tiếng.
- Giữ đúng ngữ cảnh video, địa điểm, nhân vật, quan hệ và mạch cảnh.
- Không được để sót ký tự ngôn ngữ gốc trong literal_vi, dub_vi hoặc text_vi.
- Không dùng ký tự Trung/Nhật/Hàn trong bản tiếng Việt.
- Với video vlog, ưu tiên xưng hô: "mình", "mọi người", "ở đây", "chỗ này", "phía này".
- Với lời thoại phim, dùng xưng hô theo character_bible.
- Mỗi câu phải đủ ngắn để đọc trong duration.
- Nếu câu gốc quá ngắn, có thể dịch thoát ý nhưng không thêm thông tin sai.
- Nếu câu dịch quá dài, rút gọn tự nhiên.
- Luôn trả JSON hợp lệ, không markdown, không giải thích ngoài JSON.

VIDEO_CONTEXT:
{video_context_json}

CHARACTER_BIBLE:
{character_bible_json}

GLOSSARY:
{glossary_json}

PREVIOUS_SEGMENTS:
{previous_segments_json}

TARGET_SEGMENTS:
{target_segments_json}

NEXT_SEGMENTS:
{next_segments_json}

Return JSON:
{
  "segments": [
    {
      "id": 1,
      "source_text": "...",
      "literal_vi": "...",
      "dub_vi": "...",
      "speaker": "...",
      "speaker_gender": "...",
      "pronoun_note": "...",
      "context_note": "...",
      "risk_flags": []
    }
  ]
}
```

---

## CÁC LỖI MẪU CẦN ĐẢM BẢO KHÔNG CÒN

Ví dụ lỗi hiện tại:

```text
Họ sẽ dẫn chúng ta vào đây坐 thang máy
```

Phải sửa thành dạng tự nhiên:

```text
Nhân viên sẽ dẫn mình ra thang máy.
```

Ví dụ lỗi hiện tại:

```text
Vào đây坐 thang máy lên tầng 75
```

Phải sửa thành:

```text
Từ đây mình đi thang máy lên tầng 75.
```

Ví dụ lỗi hiện tại:

```text
Đâu cũng có thể ngồi
Đâu nhìn rõ
Đâu là trong nhà
```

Phải sửa thành:

```text
Ở đây cũng ngồi được.
Chỗ này nhìn rõ hơn.
Đây là khu trong nhà.
```

---

## QUY TẮC CODE

* Không hardcode riêng cho một video mẫu.
* Không phá format output cũ.
* Có fallback khi AI provider lỗi.
* Có log rõ từng stage.
* Có report JSON cho context/validator/repair.
* Không đưa bản dịch lỗi sang TTS.
* Không render nếu còn lỗi nghiêm trọng trong bản dịch.
* Code phải modular, dễ test, dễ thay provider AI.
* Không để prompt nằm rải rác khó bảo trì; nên gom prompt template vào module rõ ràng.

## KẾT QUẢ CUỐI CÙNG CẦN BÁO CÁO

Sau khi hoàn thành, hãy báo cáo:

1. Đã tạo/cập nhật những file tài liệu nào.
2. Đã sửa những file code nào.
3. Pipeline mới chạy theo thứ tự nào.
4. Những artifact mới được sinh ra.
5. Cách chạy test.
6. Kết quả test.
7. Những hạn chế còn lại nếu có.
8. Gợi ý bước tiếp theo để nâng chất lượng speaker detection/audio diarization.
