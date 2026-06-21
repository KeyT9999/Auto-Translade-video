# Requirement: Refactor AI Provider Pipeline

## 0. Current Priority Addendum: zh-CN Subtitle-Only Quality Recovery

The provider refactor is already underway, but the most urgent production
issue is now the zh-CN to vi-VN subtitle-only quality path. The current
validator misclassifies many valid Chinese-to-Vietnamese translations as
hallucinations, which then pushes the pipeline into an unnecessary fallback
path and loses the better contextual translation, glossary choices, and
natural subtitle phrasing.

Required behavior for this addendum:

```text
ASR/contextual translation succeeds
→ validator must be language-aware for zh-CN
→ warning-only issues must not trigger fallback
→ repair must skip false positives and stop no-op loops
→ final transcript must preserve contextual translation whenever only warnings remain
→ glossary must be enforced after translation, repair, and fallback
→ subtitle-only mode may rewrite fragmented multi-segment phrases before render
```

### Mandatory deliverables

1. Fix validator false positives for zh-CN compact-source / long-Vietnamese normal translations.
2. Stop repair loops that keep retrying the same non-critical issue set.
3. Prevent fallback to legacy translation when only warnings remain.
4. Enforce glossary terms on the final transcript, including fallback output.
5. Add subtitle group rewrite for fragmented subtitle-only phrases.
6. Add automated regression tests for the zh-CN path.

### Required validator taxonomy

The validator must stop collapsing multiple problem classes into one broad
`HALLUCINATION_RISK` bucket. It now needs explicit issue classes:

```text
LENGTH_RATIO_WARNING
READABILITY_WARNING
TIMING_OVERFLOW
TRUE_HALLUCINATION
BANNED_WRONG_TERM
GLOSSARY_MISMATCH
FRAGMENTED_SUBTITLE
SOURCE_LANGUAGE_LEAK
UNTRANSLATED_TEXT
EMPTY_TEXT
MISSING_SEGMENT
INVALID_JSON
```

### Subtitle-only blocking policy

In `subtitle_only` mode, these issue types are warnings and must not trigger
fallback by themselves:

```text
LENGTH_RATIO_WARNING
READABILITY_WARNING
TIMING_OVERFLOW
FRAGMENTED_SUBTITLE
```

These remain blocking:

```text
SOURCE_LANGUAGE_LEAK
UNTRANSLATED_TEXT
EMPTY_TEXT
INVALID_JSON
MISSING_SEGMENT
TRUE_HALLUCINATION
BANNED_WRONG_TERM
```

## 1. Bối cảnh hiện tại

### Pipeline xử lý video hiện tại

```text
input video/url
→ extract audio
→ ASR (Groq Whisper → fallback Azure)
→ context_builder (Gemini → fallback Groq Llama)
→ glossary_builder (Gemini → fallback Groq Llama)
→ character_profiler (Gemini → fallback Groq Llama)
→ contextual_translator (Gemini → fallback Groq Llama)
→ translation_validator (local rules)
→ translation_repair (Gemini → fallback Groq Llama)
→ timeline_rewriter (Gemini → fallback Groq Llama)
→ SRT/ASS subtitle generation
→ TTS (LucyLab/LarVoice) — chỉ ở chế độ dub_audio
→ audio merge / video render
```

### Mapping AI provider hiện tại (audit code)

| Bước | Provider chính | Fallback | File source |
|---|---|---|---|
| ASR Whisper | Groq (`whisper-large-v3`) | Azure Speech SDK | `src/transcriber.py` |
| Video context | Gemini (`gemini-2.0-flash`) | Groq (`llama-3.3-70b-versatile`) | `src/context_builder.py` → `src/utils.py` |
| Glossary | Gemini | Groq | `src/glossary_builder.py` → `src/utils.py` |
| Character bible | Gemini | Groq | `src/character_profiler.py` → `src/utils.py` |
| Contextual translation | Gemini | Groq | `src/contextual_translator.py` → `src/utils.py` |
| Translation repair | Gemini | Groq | `src/translation_repair.py` → `src/utils.py` |
| Timeline rewriter | Gemini | Groq | `src/timeline_rewriter.py` → `src/utils.py` |
| Fallback translation (legacy) | Gemini | Groq | `src/translator.py` → `src/utils.py` |

### Vấn đề hiện tại

```text
Gemini bị quota 429 RESOURCE_EXHAUSTED
→ config.GEMINI_FAILED = True → toàn bộ fallback sang Groq
→ Groq phải gánh: context + glossary + character + translation + repair + timeline
→ Groq cũng rate limit 429 Too Many Requests
→ Dịch fail giữa chừng
→ transcript_vi.json không được tạo
→ subtitle-only/dubbing đều không render tiếp được
```

### Điểm yếu kiến trúc

1. **Không có provider abstraction**: Mỗi file (context_builder, glossary_builder, character_profiler, contextual_translator, translation_repair, timeline_rewriter, translator) đều copy/paste pattern `generate_xxx_gemini()` + `generate_xxx_groq()` riêng lẻ.
2. **API gọi trực tiếp qua 2 helper functions** trong `src/utils.py`: `call_gemini_api()` và `call_groq_api()` — không có router hay abstraction.
3. **Groq gánh dual role**: Vừa ASR Whisper, vừa LLM translation fallback. Khi Gemini chết, Groq bị overload cả 2 chiều.
4. **Không có partial save**: Nếu dịch 100 segments theo window 25, fail ở window thứ 3 → mất hết 50 segments đã dịch xong.
5. **Không có translation cache**: Mỗi lần resume/retry đều dịch lại toàn bộ từ đầu.
6. **Hardcode model names**: `llama-3.3-70b-versatile` và `gemini-2.0-flash` nằm cứng trong code, không qua env.

---

## 2. Kiến trúc provider mới

### Thiết kế 3 tầng provider

```text
┌─────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  ASR Layer   │     │  Translation Layer   │     │   QA/Repair Layer   │
│  (Groq)      │     │  (DeepSeek)          │     │   (OpenAI mini)     │
└──────┬───────┘     └──────────┬───────────┘     └──────────┬──────────┘
       │                        │                             │
       │  whisper-large-v3      │  deepseek-v4-flash          │  gpt-4o-mini
       │                        │  (OpenAI-compatible API)    │
       ▼                        ▼                             ▼
   transcribe()            translate()                   repair()
                           generate_context()            normalize_json()
                           generate_glossary()           remove_cjk_leak()
                           generate_character_bible()    rewrite_subtitle()
```

### Mapping mặc định

```env
ASR_PROVIDER=groq
TRANSLATION_PROVIDER=deepseek
QA_REPAIR_PROVIDER=openai
```

### Groq — ASR Whisper only

- **Vai trò**: ASR (Speech-to-Text) duy nhất.
- **Không dùng** cho translation mặc định nữa (trừ khi người dùng bật fallback).
- Model mặc định: `GROQ_ASR_MODEL=whisper-large-v3`
- Hỗ trợ model thay thế: `whisper-large-v3-turbo`

### DeepSeek — Translation provider chính

- **Vai trò**: Dịch thuật chính — giá rẻ, output tốt cho bài toán dịch nhiều segment.
- Dùng cho:
  - `video_context` generation
  - `glossary` generation
  - `character_bible` generation
  - `contextual_translation` (sliding window)
  - `subtitle_vi` generation
  - `literal_vi`, `dub_vi` generation
- Model mặc định: `DEEPSEEK_MODEL=deepseek-v4-flash`
- Gọi qua **OpenAI-compatible API** (`base_url=https://api.deepseek.com`)
- Nếu tên model thực tế khác `deepseek-v4-flash`, user tự đổi qua env.

### OpenAI mini — QA/Repair provider

- **Vai trò**: Sửa lỗi, kiểm tra chất lượng — cần độ ổn định cao.
- Dùng cho:
  - JSON schema validation/normalization
  - Translation repair (CJK leak, source-language leak)
  - Untranslated text repair
  - Vietnamese fluency rewrite
  - Subtitle quality rewrite
  - Timeline/subtitle concise rewrite
- Model mặc định: `OPENAI_REPAIR_MODEL=gpt-4o-mini`
- Cho phép cấu hình model khác qua env.

---

## 3. Env config mới

Thêm/cập nhật `.env.example`:

```env
# =========================
# AI Provider Routing
# =========================
ASR_PROVIDER=groq
TRANSLATION_PROVIDER=deepseek
QA_REPAIR_PROVIDER=openai

# Optional fallback chain (comma-separated)
TRANSLATION_FALLBACK_PROVIDERS=openai,groq
QA_REPAIR_FALLBACK_PROVIDERS=deepseek,groq

# Disable Gemini by default (set to true to re-enable)
GEMINI_ENABLED=false

# =========================
# Groq ASR
# =========================
GROQ_API_KEY=
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_ASR_MODEL=whisper-large-v3
GROQ_ASR_LANGUAGE_AUTO=false

# =========================
# DeepSeek Translation
# =========================
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_MS=60000
DEEPSEEK_MAX_RETRIES=5
DEEPSEEK_MIN_DELAY_MS=1500

# =========================
# OpenAI QA / Repair
# =========================
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_REPAIR_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_MS=60000
OPENAI_MAX_RETRIES=5

# =========================
# Translation Pipeline Controls
# =========================
TRANSLATION_WINDOW_SIZE=35
TRANSLATION_CONTEXT_BEFORE=3
TRANSLATION_CONTEXT_AFTER=3
TRANSLATION_CACHE_ENABLED=true
TRANSLATION_PARTIAL_SAVE_ENABLED=true
TRANSLATION_FAIL_ON_CJK=true
TRANSLATION_FAIL_ON_UNTRANSLATED_TEXT=true
TRANSLATION_MAX_REPAIR_ROUNDS=2

# Subtitle-only mode
SUBTITLE_ONLY_TIMING_OVERFLOW_IS_WARNING=true
```

---

## 4. Provider abstraction bắt buộc

### Cấu trúc thư mục

```text
src/ai/
  __init__.py
  base.py              ← Abstract base classes
  groq_provider.py     ← Groq ASR + optional LLM
  deepseek_provider.py ← DeepSeek translation (OpenAI-compatible)
  openai_provider.py   ← OpenAI repair/QA
  gemini_provider.py   ← Legacy Gemini (disabled by default)
  router.py            ← Central routing logic
```

### Interface bắt buộc

```python
# base.py
class TextAIProvider(ABC):
    """Base class for LLM text generation providers."""
    @abstractmethod
    def generate_text(self, prompt: str, temperature: float = 0.2, **kwargs) -> str: ...

    @abstractmethod
    def generate_json(self, prompt: str, temperature: float = 0.2, **kwargs) -> dict: ...

class ASRProvider(ABC):
    """Base class for speech-to-text providers."""
    @abstractmethod
    def transcribe(self, audio_path: str, language: str | None = None) -> list[dict]: ...
```

### Router API

```python
# router.py
ai_router.asr(audio_path, language)
ai_router.translate(prompt, **kwargs)          # → TRANSLATION_PROVIDER
ai_router.repair(prompt, **kwargs)             # → QA_REPAIR_PROVIDER
ai_router.generate_context(prompt, **kwargs)   # → TRANSLATION_PROVIDER
ai_router.generate_glossary(prompt, **kwargs)  # → TRANSLATION_PROVIDER
ai_router.generate_character_bible(prompt, **kwargs)  # → TRANSLATION_PROVIDER
ai_router.rewrite_timeline(prompt, **kwargs)   # → QA_REPAIR_PROVIDER
```

Provider selection dựa trên env config, có fallback chain. **Không hardcode.**

---

## 5. DeepSeek provider

### Yêu cầu kỹ thuật

- Gọi chat completion theo OpenAI-compatible format (dùng `openai` Python SDK hoặc `requests` trực tiếp).
- `base_url` cấu hình qua env: `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- Hỗ trợ JSON output (hướng dẫn trong prompt + parse response).
- Có retry/exponential backoff.
- Log rõ ràng: `provider=deepseek`, `model=deepseek-v4-flash`, `stage=translation`, `retry=2/5`.
- **Không log API key.**
- Parse JSON an toàn: strip markdown fences nếu có.
- Nếu JSON parse lỗi → trả lỗi để QA_REPAIR_PROVIDER (OpenAI) normalize.

### Function tối thiểu

```python
class DeepSeekProvider(TextAIProvider):
    def generate_text(self, prompt: str, temperature: float = 0.2, **kwargs) -> str: ...
    def generate_json(self, prompt: str, temperature: float = 0.2, **kwargs) -> dict: ...
```

---

## 6. OpenAI repair provider

### Vai trò

OpenAI mini **không dùng dịch chính** mặc định. Chỉ dùng cho:

- Repair bad segments (CJK leak, untranslated text)
- Normalize malformed JSON responses
- Improve awkward Vietnamese phrasing
- Subtitle formatting/rewrite
- Timeline rewrite (shorten/expand)

### Repair prompt input

```text
VIDEO_CONTEXT
GLOSSARY
CHARACTER_BIBLE
VALIDATOR_ISSUES
BAD_SEGMENTS
```

### Repair prompt output

```json
{
  "segments": [
    {
      "id": 1,
      "literal_vi": "...",
      "dub_vi": "...",
      "subtitle_vi": "...",
      "text_vi": "..."
    }
  ]
}
```

### Quy tắc repair

- Không đổi `id`, `start`, `end`, `duration`.
- Không sửa segment không lỗi.
- Không để sót ký tự Trung/Nhật/Hàn trong tiếng Việt.
- Không để tiếng Anh/Trung chưa dịch.
- Subtitle-only: ưu tiên `subtitle_vi`.
- Dubbing: ưu tiên `dub_vi` / `final_dub_vi`.
- Tiếng Việt phải tự nhiên, ngắn gọn, phù hợp video ngắn.

---

## 7. Translation provider dùng DeepSeek

### Các bước PHẢI chuyển sang DeepSeek mặc định

| Bước | Trước (Gemini → Groq) | Sau (DeepSeek → fallback chain) |
|---|---|---|
| `build_video_context()` | `call_gemini_api()` → `call_groq_api()` | `ai_router.generate_context()` |
| `build_glossary()` | `call_gemini_api()` → `call_groq_api()` | `ai_router.generate_glossary()` |
| `build_character_bible()` | `call_gemini_api()` → `call_groq_api()` | `ai_router.generate_character_bible()` |
| `translate_segments_contextual()` | `call_gemini_api()` → `call_groq_api()` | `ai_router.translate()` |
| `translate_segments()` (legacy) | `call_gemini_api()` → `call_groq_api()` | `ai_router.translate()` |

### Khi `GEMINI_ENABLED=false`

- Không gọi Gemini.
- Log gọn: `"Gemini disabled by config. Using DeepSeek for translation pipeline."`
- Không spam lỗi Gemini 429.

---

## 8. Fallback behavior

### Fallback chain mới

```text
Translation: DeepSeek → OpenAI → Groq (optional)
Repair:      OpenAI  → DeepSeek → Groq (optional)
ASR:         Groq    → Azure Speech SDK (existing fallback)
```

### Khi provider bị 429

1. Respect `Retry-After` header nếu có.
2. Không spam request liên tục.
3. Exponential backoff: `delay = base_delay * (2 ** attempt)`.
4. Lưu partial translation trước khi chờ/retry.
5. Nếu vượt max retries → chuyển sang provider kế tiếp trong fallback chain.
6. Nếu hết toàn bộ fallback chain → ghi pending file rõ ràng, dừng pipeline.

---

## 9. Partial save và resume

### Window save

Khi dịch theo window, lưu kết quả mỗi window thành công:

```text
<work_dir>/translation_windows/window_001_025.json
<work_dir>/translation_windows/window_026_050.json
<work_dir>/translation_windows/window_051_075.json
```

Nếu window bị lỗi/rate limit:

```text
<work_dir>/translation_windows/window_051_075.pending.json
```

### Resume logic

1. Đọc lại tất cả window file đã dịch thành công.
2. Chỉ dịch window còn thiếu hoặc `.pending`.
3. **Không gọi lại toàn bộ từ đầu.**
4. Khi tất cả window đủ → merge thành `transcript_vi.json`.

---

## 10. Translation cache

### Cache key (hash)

```text
source_language + target_language + hash(transcript_original.json) + translation_style + provider_model
```

### Cache path

```text
.cache/translations/<hash>.json
```

### Flow

1. Tính hash transcript.
2. Nếu cache hit → load `transcript_vi.json` từ cache, skip toàn bộ translation.
3. Nếu cache miss → dịch bình thường.
4. Sau khi dịch xong + validator pass → save cache.
5. Cho phép tắt: `TRANSLATION_CACHE_ENABLED=false`.

---

## 11. Validator theo mode

### Dubbing mode

- `TIMING_OVERFLOW` có thể warning hoặc block tùy config.
- Field ưu tiên: `final_dub_vi > dub_vi > text_vi > literal_vi`.

### Subtitle-only mode

- `TIMING_OVERFLOW` chỉ là warning, không block render.
- Chỉ block khi:
  - CJK/source-language leak
  - Text empty
  - Untranslated text
  - Missing segment
  - Invalid JSON
- Field ưu tiên: `subtitle_vi > text_vi > dub_vi > literal_vi`.

---

## 12. Không phá mode cũ

### Dubbing mode (giữ nguyên)

```text
DeepSeek dịch chính → OpenAI repair → TTS provider hiện tại → audio fit → audio merge → dubbed_video.mp4
```

### Subtitle-only mode (giữ nguyên)

```text
DeepSeek dịch chính → OpenAI repair → generate SRT/ASS → optional cover subtitles → burn subtitle → subtitled_video.mp4 (giữ nguyên audio gốc)
```

Không để subtitle-only gọi TTS/audio merge.

---

## 13. Acceptance Criteria

Hoàn thành khi:

- [ ] Có `requirement.md` (file này).
- [ ] Có `task.md` (checklist thực thi).
- [ ] `.env.example` có provider config mới.
- [ ] Groq chỉ làm ASR mặc định.
- [ ] DeepSeek làm translation provider mặc định.
- [ ] OpenAI mini làm QA/repair provider mặc định.
- [ ] Gemini không còn bị gọi khi `GEMINI_ENABLED=false`.
- [ ] Pipeline tạo được:
  - `video_context.json`
  - `glossary.json`
  - `character_bible.json`
  - `transcript_vi.json`
  - `translation_quality_report.json`
  - `translation_repair_report.json` (nếu có lỗi)
- [ ] Có partial save window.
- [ ] Có resume window bị thiếu.
- [ ] Có cache translation.
- [ ] Subtitle-only render không cần TTS.
- [ ] Nếu có CJK/source-language leak thì OpenAI repair xử lý.
- [ ] Nếu repair vẫn fail thì stop rõ ràng, không render phụ đề lỗi.
- [ ] Có test hoặc script kiểm tra provider routing.
- [ ] Tất cả AI stages ghi `provider=xxx`, `model=xxx` vào log.

---

## 14. Prompt dịch chính cho DeepSeek

*(Dùng cho contextual translation)*

```text
Bạn là biên dịch viên chuyên dịch video ngắn từ {source_language} sang tiếng Việt.

Nhiệm vụ:
- Dịch tự nhiên cho người Việt xem video ngắn.
- Không dịch từng chữ máy móc.
- Giữ đúng ngữ cảnh video, nhân vật, địa điểm, quan hệ, mạch cảnh.
- Không để sót ký tự tiếng Trung/Nhật/Hàn trong bản tiếng Việt.
- Không để sót tiếng Anh/source text chưa dịch.
- Với vlog, ưu tiên xưng hô: mình, mọi người, các bạn.
- Với phim/drama, dùng xưng hô theo character_bible.
- Tạo đủ các field:
  - literal_vi: bản dịch nghĩa
  - subtitle_vi: bản phụ đề tự nhiên, dễ đọc
  - dub_vi: bản lời thoại ngắn nếu cần TTS
  - text_vi: alias tương thích, ưu tiên bằng subtitle_vi
- Với subtitle-only, subtitle_vi là quan trọng nhất.
- Với dubbing, dub_vi phải ngắn gọn để đọc được.
- Không bịa thêm thông tin ngoài transcript.
- Trả JSON hợp lệ duy nhất, không markdown, không giải thích.
```

---

## 15. Prompt repair cho OpenAI mini

```text
Bạn là reviewer phụ đề tiếng Việt và JSON repair agent.

Bạn nhận được danh sách segment dịch lỗi. Hãy sửa CHỈ các segment lỗi.

Quy tắc:
- Không đổi id/start/end/duration.
- Không sửa segment không có trong danh sách.
- Không để sót ký tự Trung/Nhật/Hàn.
- Không để sót tiếng Anh hoặc source language chưa dịch.
- Tiếng Việt phải tự nhiên, ngắn gọn, phù hợp video ngắn.
- Nếu field literal_vi lỗi nhưng subtitle_vi đúng, vẫn sửa literal_vi.
- Với subtitle-only, ưu tiên sửa subtitle_vi và text_vi.
- Với dubbing, ưu tiên sửa dub_vi.
- Trả JSON hợp lệ duy nhất, không markdown.
```
