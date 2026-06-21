# Task: Refactor AI Provider Pipeline — Checklist

---

## Phase 0: Audit code ✅

Đã audit toàn bộ codebase. Kết quả:

| Chức năng | File hiện tại | Gọi AI qua |
|---|---|---|
| **Groq ASR Whisper** | `src/transcriber.py` → `transcribe_groq()` | Trực tiếp `requests.post()` đến `api.groq.com` |
| **Azure ASR fallback** | `src/transcriber.py` → `transcribe()` | Azure Speech SDK |
| **Gemini LLM** | `src/utils.py` → `call_gemini_api()` | `google.genai` SDK |
| **Groq LLM (Llama)** | `src/utils.py` → `call_groq_api()` | `requests.post()` đến `api.groq.com/openai/v1` |
| **Context builder** | `src/context_builder.py` | `call_gemini_api()` → `call_groq_api()` |
| **Glossary builder** | `src/glossary_builder.py` | `call_gemini_api()` → `call_groq_api()` |
| **Character profiler** | `src/character_profiler.py` | `call_gemini_api()` → `call_groq_api()` |
| **Contextual translator** | `src/contextual_translator.py` | `call_gemini_api()` → `call_groq_api()` |
| **Legacy translator** | `src/translator.py` | `call_gemini_api()` → `call_groq_api()` |
| **Translation repair** | `src/translation_repair.py` | `call_gemini_api()` → `call_groq_api()` |
| **Timeline rewriter** | `src/timeline_rewriter.py` | `call_gemini_api()` → `call_groq_api()` |
| **Translation validator** | `src/translation_validator.py` | Local rules (no AI call) |
| **SRT/ASS generator** | `src/srt_generator.py`, `src/subtitle_renderer.py` | Local (no AI call) |
| **Pipeline orchestrator** | `pipeline_vi.py` | Imports tất cả modules trên |
| **Web API** | `web_server.py` | Gọi `run_pipeline_vi()` |
| **Config loader** | `config.py` | Đọc `.env` |

### Pattern lặp lại trong code

Mỗi module (`context_builder`, `glossary_builder`, `character_profiler`, `contextual_translator`, `translation_repair`, `timeline_rewriter`, `translator`) đều có pattern giống nhau:

```python
def generate_xxx_gemini(prompt) -> X | None:
    from src.utils import call_gemini_api
    res = call_gemini_api(prompt)
    # parse json...

def generate_xxx_groq(prompt) -> X | None:
    from src.utils import call_groq_api
    res = call_groq_api(prompt)
    # parse json...

def build_xxx():
    result = generate_xxx_gemini(prompt)
    if not result:
        result = generate_xxx_groq(prompt)
```

→ **7 file, mỗi file 2 hàm riêng, tổng 14 hàm gọi AI cần refactor.**

---

## Phase 1: Config/env ✅

- [x] Thêm env variables mới vào `config.py`:
  - `ASR_PROVIDER`, `TRANSLATION_PROVIDER`, `QA_REPAIR_PROVIDER`
  - `TRANSLATION_FALLBACK_PROVIDERS`, `QA_REPAIR_FALLBACK_PROVIDERS`
  - `GEMINI_ENABLED`
  - `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`, `DEEPSEEK_TIMEOUT_MS`, `DEEPSEEK_MAX_RETRIES`, `DEEPSEEK_MIN_DELAY_MS`
  - `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_REPAIR_MODEL`, `OPENAI_TIMEOUT_MS`, `OPENAI_MAX_RETRIES`
  - `GROQ_BASE_URL`, `GROQ_ASR_LANGUAGE_AUTO`
  - `TRANSLATION_WINDOW_SIZE`, `TRANSLATION_CONTEXT_BEFORE`, `TRANSLATION_CONTEXT_AFTER`
  - `TRANSLATION_CACHE_ENABLED`, `TRANSLATION_PARTIAL_SAVE_ENABLED`
  - `TRANSLATION_FAIL_ON_CJK`, `TRANSLATION_FAIL_ON_UNTRANSLATED_TEXT`
  - `TRANSLATION_MAX_REPAIR_ROUNDS`
- [x] Cập nhật `.env.example` với tất cả config mới + comments
- [x] Validate thiếu API key:
  - Nếu `ASR_PROVIDER=groq` mà thiếu `GROQ_API_KEY` → lỗi rõ
  - Nếu `TRANSLATION_PROVIDER=deepseek` mà thiếu `DEEPSEEK_API_KEY` → lỗi rõ
  - Nếu `QA_REPAIR_PROVIDER=openai` mà thiếu `OPENAI_API_KEY` → lỗi rõ
- [x] Giữ backward compatibility: nếu `.env` cũ không có các biến mới → dùng default hợp lý

---

## Phase 2: Provider abstraction ✅

- [x] Tạo `src/ai/__init__.py`
- [x] Tạo `src/ai/base.py`:
  ```python
  class TextAIProvider(ABC):
      provider_name: str
      model_name: str
      def generate_text(self, prompt: str, temperature: float = 0.2, **kwargs) -> str: ...
      def generate_json(self, prompt: str, temperature: float = 0.2, **kwargs) -> dict: ...

  class ASRProvider(ABC):
      provider_name: str
      def transcribe(self, audio_path: str, language: str | None = None) -> list[dict]: ...
  ```
- [x] Implement `_strip_markdown_fences()` utility trong base
- [x] Implement `_safe_parse_json()` utility trong base

---

## Phase 3: DeepSeek provider ✅

- [x] Tạo `src/ai/deepseek_provider.py`
- [x] Implement `DeepSeekProvider(TextAIProvider)`:
  - `__init__`: load API key, base_url, model từ config
  - `generate_text()`: gọi OpenAI-compatible chat completion
  - `generate_json()`: gọi chat completion + parse JSON an toàn
- [x] Hỗ trợ `DEEPSEEK_BASE_URL` (default: `https://api.deepseek.com`)
- [x] Hỗ trợ `DEEPSEEK_MODEL` từ env
- [x] Timeout: `DEEPSEEK_TIMEOUT_MS`
- [x] Retry/exponential backoff: `DEEPSEEK_MAX_RETRIES` lần, delay bắt đầu từ `DEEPSEEK_MIN_DELAY_MS`
- [x] Respect `Retry-After` header khi 429
- [x] Strip ```json fences từ response
- [x] Log rõ: `provider=deepseek`, `model=xxx`, `stage=xxx`, `retry=n/N`
- [x] **Không log API key**
- [x] Nếu JSON parse lỗi → raise error rõ ràng để router có thể fallback hoặc chuyển sang QA repair

---

## Phase 4: OpenAI repair provider ✅

- [x] Tạo `src/ai/openai_provider.py`
- [x] Implement `OpenAIProvider(TextAIProvider)`:
  - `__init__`: load API key, base_url, model từ config
  - `generate_text()`: gọi OpenAI chat completion
  - `generate_json()`: gọi + parse JSON
- [x] Hỗ trợ `OPENAI_BASE_URL`, `OPENAI_REPAIR_MODEL`
- [x] Timeout, retry/backoff như DeepSeek
- [x] Không dùng OpenAI dịch chính nếu config không chọn (`TRANSLATION_PROVIDER != openai`)
- [x] Tạo repair prompts chuyên biệt (trong module gọi, không trong provider):
  - Repair CJK leak
  - Repair untranslated text
  - Normalize malformed JSON
  - Improve awkward Vietnamese
  - Subtitle rewrite

---

## Phase 5: Gemini provider (legacy, disabled by default) ✅

- [x] Tạo `src/ai/gemini_provider.py`
- [x] Wrap `call_gemini_api()` logic hiện tại vào class `GeminiProvider(TextAIProvider)`
- [x] Kiểm tra `GEMINI_ENABLED` trước khi gọi
- [x] Nếu `GEMINI_ENABLED=false` → skip, không log lỗi
- [x] Nếu 429 → set flag, không retry quá nhiều

---

## Phase 6: Groq provider (refactored) ✅

- [x] Tạo `src/ai/groq_provider.py`
- [x] `GroqASRProvider(ASRProvider)`:
  - Wrap logic `transcribe_groq()` hiện tại
  - Dùng `GROQ_ASR_MODEL` từ config
  - Dùng `GROQ_BASE_URL` từ config
- [x] `GroqLLMProvider(TextAIProvider)` (optional, cho fallback):
  - Wrap logic `call_groq_api()` hiện tại
  - Chỉ dùng khi nằm trong fallback chain

---

## Phase 7: Provider router ✅

- [x] Tạo `src/ai/router.py`
- [x] Implement class `AIRouter`:
  ```python
  def asr(self, audio_path, language) -> list[dict]
  def translate(self, prompt, **kwargs) -> dict
  def repair(self, prompt, **kwargs) -> dict
  def generate_context(self, prompt, **kwargs) -> dict
  def generate_glossary(self, prompt, **kwargs) -> dict
  def generate_character_bible(self, prompt, **kwargs) -> dict
  def rewrite_timeline(self, prompt, **kwargs) -> dict
  ```
- [x] Provider selection dựa trên config:
  ```text
  asr → ASR_PROVIDER (groq)
  translate/context/glossary/character → TRANSLATION_PROVIDER (deepseek)
  repair/rewrite → QA_REPAIR_PROVIDER (openai)
  ```
- [x] Fallback chain từ env:
  ```text
  TRANSLATION_FALLBACK_PROVIDERS=openai,groq
  QA_REPAIR_FALLBACK_PROVIDERS=deepseek,groq
  ```
- [x] Khi provider 429:
  - Respect retry-after
  - Exponential backoff
  - Partial save trước khi chờ/retry
  - Nếu hết retry → chuyển sang provider kế tiếp trong chain
- [x] Tạo singleton/global router instance: `ai_router = AIRouter()`
- [x] Log mỗi AI call: `[provider=deepseek model=deepseek-v4-flash stage=translation]`

---

## Phase 8: Refactor translation pipeline modules ✅

Sửa các file để không gọi trực tiếp Gemini/Groq nữa, mà gọi qua `ai_router`:

- [x] **`src/context_builder.py`**:
  - Xóa `generate_context_gemini()`, `generate_context_groq()`
  - `build_video_context()` → gọi `ai_router.generate_context(prompt)`
- [x] **`src/glossary_builder.py`**:
  - Xóa `generate_glossary_gemini()`, `generate_glossary_groq()`
  - `build_glossary()` → gọi `ai_router.generate_glossary(prompt)`
- [x] **`src/character_profiler.py`**:
  - Xóa `generate_bible_gemini()`, `generate_bible_groq()`
  - `build_character_bible()` → gọi `ai_router.generate_character_bible(prompt)`
- [x] **`src/contextual_translator.py`**:
  - Xóa `translate_window_gemini()`, `translate_window_groq()`
  - `translate_segments_contextual()` → gọi `ai_router.translate(prompt)`
  - Cập nhật prompt theo mẫu mới từ requirement.md
  - Thêm `subtitle_vi` field vào output
  - Dùng `TRANSLATION_WINDOW_SIZE` từ config thay vì hardcode `25`
- [x] **`src/translation_repair.py`**:
  - Xóa `repair_gemini()`, `repair_groq()`
  - `repair_translation()` → gọi `ai_router.repair(prompt)`
  - Cập nhật prompt theo mẫu mới
- [x] **`src/timeline_rewriter.py`**:
  - Xóa `rewrite_gemini()`, `rewrite_groq()`
  - `rewrite_timeline()` → gọi `ai_router.rewrite_timeline(prompt)`
- [x] **`src/translator.py`** (legacy fallback):
  - Xóa `translate_gemini()`, `translate_groq()`
  - `translate_segments()` → gọi `ai_router.translate(prompt)`
- [x] **`src/transcriber.py`**:
  - `transcribe()` → gọi `ai_router.asr(audio_path, language)` thay vì gọi trực tiếp `transcribe_groq()`
  - Giữ Azure fallback trong router hoặc trong transcriber

---

## Phase 9: Window partial save ✅

- [x] Tạo thư mục `<work_dir>/translation_windows/` khi bắt đầu dịch
- [x] Sau mỗi window dịch thành công → lưu `window_001_025.json`
- [x] Nếu window fail → lưu `window_026_050.pending.json` (chứa metadata lỗi)
- [x] Implement resume logic trong `contextual_translator.py`:
  - Quét thư mục `translation_windows/`
  - Nếu window file đã có (không phải `.pending`) → skip
  - Nếu window thiếu hoặc `.pending` → dịch lại window đó
  - Khi tất cả window đủ → merge thành `transcript_vi.json`
- [x] Đảm bảo `TRANSLATION_PARTIAL_SAVE_ENABLED` config hoạt động (mặc định `true`)

---

## Phase 10: Translation cache ✅

- [x] Tạo thư mục `.cache/translations/` (gitignore)
- [x] Tính hash transcript:
  ```text
  hash = md5(source_language + target_language + json_content + provider_model)
  ```
- [x] Trước khi dịch → check cache hit → nếu có, load trực tiếp
- [x] Sau khi dịch xong + validator pass → save cache
- [x] Config: `TRANSLATION_CACHE_ENABLED=true/false`
- [x] Thêm `.cache/` vào `.gitignore`

---

## Phase 11: Validator/repair flow ✅

### Flow mới trong `pipeline_vi.py`

```text
DeepSeek translate (via ai_router)
→ validator (local rules)
→ if bad segments:
      OpenAI repair (via ai_router)
      → validator again
→ if still bad (round 2):
      OpenAI repair again
      → validator again
→ if still bad after TRANSLATION_MAX_REPAIR_ROUNDS:
      fallback repair provider hoặc stop rõ ràng
→ save transcript_vi.json
```

- [x] Implement repair loop với `TRANSLATION_MAX_REPAIR_ROUNDS=2`
- [x] Không để bản dịch lỗi CJK/source-language leak đi tiếp render/TTS
- [x] Log rõ ràng số lần repair và kết quả mỗi round

---

## Phase 12: Mode-aware behavior (verification) ✅

- [x] Subtitle-only mode:
  - Không block `TIMING_OVERFLOW` (chỉ warning)
  - Không gọi TTS
  - Không audio merge
  - Render subtitle nếu đủ `transcript_vi`
  - Field ưu tiên: `subtitle_vi > text_vi > dub_vi > literal_vi`
- [x] Dubbing mode:
  - Dùng `dub_vi` / `final_dub_vi`
  - Vẫn timing-aware rewrite
  - TTS như cũ
  - Field ưu tiên: `final_dub_vi > dub_vi > text_vi > literal_vi`
- [x] Không phá logic mode cũ

---

## Phase 13: Tests/tools ✅

### Unit tests

- [x] `tests/test_ai_router.py`:
  - Provider routing test (config → đúng provider)
  - Fallback chain test
  - Gemini disabled test
  - Groq only ASR test (không dịch mặc định)
- [x] `tests/test_deepseek_provider.py`:
  - JSON parse test
  - Markdown fence strip test
  - Retry/backoff mock test
- [x] `tests/test_openai_provider.py`:
  - Repair prompt test
  - JSON normalize test
- [x] `tests/test_partial_save.py`:
  - Window save/load test
  - Resume skip completed windows test
  - Merge windows test
- [x] `tests/test_translation_cache.py`:
  - Cache hit test
  - Cache miss → save test
  - Cache disabled test
- [x] Cập nhật `tests/test_subtitle_only.py`:
  - Verify subtitle-only does not call TTS
  - Verify subtitle-only does not block timing overflow

### Scripts

- [x] `tools/check_ai_provider_routing.py`:
  - Kiểm tra config → provider routing
  - Kiểm tra API key validation
  - Kiểm tra fallback chain
- [x] `tools/check_translation_session.py`:
  - Kiểm tra output session directory
  - Validate `transcript_vi.json`
  - Report CJK leak nếu có

---

## Phase 14: Cleanup ✅

- [x] Xóa/deprecate `call_gemini_api()` và `call_groq_api()` trong `src/utils.py` (hoặc giữ wrapper đơn giản gọi qua router)
- [x] Xóa tất cả `generate_xxx_gemini()` / `generate_xxx_groq()` riêng lẻ trong các modules
- [x] Cập nhật imports trong `pipeline_vi.py`
- [x] Cập nhật `web_server.py` nếu cần thêm field API
- [x] Cập nhật `README.md` với hướng dẫn provider config mới

---

## Phase 15: Final report ✅

Sau khi code xong, báo cáo:

1. Đã tạo/cập nhật `requirement.md` ở `Task/APIAI/requirement.md`
2. Đã tạo/cập nhật `task.md` ở `Task/APIAI/task.md`
3. Danh sách file đã sửa
4. Provider routing mới hoạt động ra sao
5. Env cần thêm gì
6. CLI/Web UI có cần đổi không
7. Cách chạy test
8. Kết quả test
9. Hạn chế còn lại
# Addendum: zh-CN Subtitle-Only Quality Patch

- [ ] Fix validator false-positive for zh-CN compact-source / long-Vietnamese normal translations
- [ ] Split the old broad hallucination rule into `LENGTH_RATIO_WARNING`, `READABILITY_WARNING`, `TRUE_HALLUCINATION`, `BANNED_WRONG_TERM`, `GLOSSARY_MISMATCH`, and `FRAGMENTED_SUBTITLE`
- [ ] Add validator config knobs for zh-CN vs generic length policy
- [ ] Make subtitle-only timing/length pressure warnings instead of blockers
- [ ] Prevent repair loop retries when issue count/text does not improve
- [ ] Limit AI repair to genuinely critical issue types
- [ ] Keep contextual translation whenever only warnings remain
- [ ] Make fallback translation pass through glossary enforcement and final QA
- [ ] Add `src/glossary_enforcer.py`
- [ ] Add `src/subtitle_group_rewriter.py`
- [ ] Enforce glossary after contextual translation, after repair, and after fallback
- [ ] Add zh-CN term normalization for noisy ASR/source variants
- [ ] Add subtitle group rewrite for fragmented 2–4 segment subtitle phrases
- [ ] Add regression tests for validator, fallback policy, glossary, and subtitle rewrite
