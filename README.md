# 🎬 Auto-Translade-video
python web_server.py

Hệ thống tự động lồng tiếng video chuyên nghiệp (hỗ trợ các nền tảng YouTube, TikTok, Douyin hoặc file cục bộ local) sang **tiếng Việt** hoặc **tiếng Nhật**. Hệ thống hoạt động hoàn chỉnh từ khâu tải video, tách âm nền/nhạc nền gốc bằng AI, nhận dạng giọng nói (ASR), dịch thuật tối ưu hóa ngữ cảnh và xưng hô, nhận diện nhân vật (Speaker Detection), tổng hợp giọng nói tự nhiên (TTS), căn chỉnh khớp timeline, sinh siêu dữ liệu (Metadata) SEO kèm ảnh đại diện (Thumbnail), và cuối cùng là tự động xuất bản (Publish) lên YouTube và Facebook Page.

Dự án cung cấp cả giao diện **Web UI hiện đại (Glassmorphism Dark Terminal)** trực quan lẫn giao diện dòng lệnh **CLI** mạnh mẽ và các công cụ chạy hàng loạt (Batch run) qua danh sách file Excel/JSON.

---

## 📚 Mục lục
1. [Mục tiêu & Mục đích dự án](#-mục-tiêu--mục-đích-dự-án)
2. [Cơ cấu Quy trình Hoạt động (Pipeline Workflow)](#-cơ-cấu-quy-trình-hoạt-động-pipeline-workflow)
3. [Công nghệ áp dụng (Technology Stack)](#-công-nghệ-áp-dụng-technology-stack)
4. [Cấu trúc Thư mục Nguồn (Source Directory Structure)](#-cấu-trúc-thư-mục-nguồn-source-directory-structure)
5. [Cài đặt & Yêu cầu Hệ thống](#-cài-đặt--yêu-cầu-hệ-thống)
6. [Cấu hình biến môi trường (.env)](#-cấu-hình-biến-môi-trường-env)
7. [Hướng dẫn Sử dụng](#-hướng-dẫn-sử-dụng)
   - [Cách 1: Giao diện Web UI (Khuyến nghị)](#cách-1-sử-dụng-giao-diện-web-ui-khuyến-nghị)
   - [Cách 2: Chạy CLI (Dòng lệnh đơn lẻ)](#cách-2-sử-dụng-dòng-lệnh-cli-dòng-lệnh-đơn-lẻ)
   - [Cách 3: Xử lý Hàng loạt (Batch Process)](#cách-3-xử-lý-hàng-loạt-batch-process)
   - [Các công cụ phụ trợ hữu ích](#các-công-cụ-phụ-trợ-hữu-ích)
8. [Cấu trúc Thư mục Đầu ra (Output Structure)](#-cấu-trúc-thư-mục-đầu-ra-output-structure)
9. [Quy trình Hậu kỳ với phần mềm Edit Video (CapCut)](#-quy-trình-hậu-kỳ-với-phần-mềm-edit-video-capcut)
10. [Chạy Kiểm thử (Unit Tests)](#-chạy-kiểm-thử-unit-tests)
11. [Ước tính Chi phí Hoạt động](#-ước-tính-chi-phí-hoạt-động)
12. [Hạn chế hiện tại & Lưu ý pháp lý](#-hạn-chế-hiện-tại--lưu-ý-pháp-lý)

---

## 🎯 Mục tiêu & Mục đích Dự án

Khi chuyển ngữ một video nước ngoài, phương pháp dịch phụ đề truyền thống thường làm người xem mất tập trung vào hình ảnh, trong khi việc lồng tiếng thủ công tốn kém rất nhiều thời gian và chi phí phòng thu. Dự án này được thiết kế để **tự động hóa toàn bộ quy trình lồng tiếng (Automated Dubbing)** bằng cách kết hợp những công nghệ AI tiên tiến nhất hiện nay:
*   **Giữ nguyên hồn cốt của video gốc**: Tách giọng nói của người nói ra khỏi âm thanh nền, giữ lại 100% âm thanh môi trường, tiếng động (SFX) và nhạc nền sạch sẽ.
*   **Dịch thuật tự nhiên như người bản xứ**: Không chỉ dịch thô, AI phân tích giới tính, vai trò nhân vật để xưng hô tự nhiên (ví dụ giữa mẹ-con, vợ-chồng, bạn-bè) theo ngữ cảnh phim truyền hình/drama.
*   **Đồng bộ hóa thời gian tự động**: Audio lồng tiếng tự động tăng/giảm tốc độ phù hợp với trường đoạn của nhân vật gốc, tránh tình trạng nói đè, chồng chéo.
*   **Khép kín từ đầu vào đến đầu ra**: Chỉ cần cung cấp link video gốc, hệ thống sẽ tự động đăng tải video lồng tiếng thành phẩm lên các kênh mạng xã hội với đề xuất SEO hoàn chỉnh.

---

## 🔄 Cơ cấu Quy trình Hoạt động (Pipeline Workflow)

Dưới đây là sơ đồ chi tiết quy trình xử lý của hệ thống:

```
                  ┌─────────────────────────────────────────┐
                  │               USER INPUT                │
                  │   Link (YouTube/TikTok/Douyin) hoặc File │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │        Bước 1: Tải Video (yt-dlp)       │
                  │ (Playwright Chromium đối với Douyin)    │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │    Bước 2: Trích xuất Audio (FFmpeg)    │
                  │        => original_audio.wav            │
                  └────────────────────┬────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼ (Demucs Mode)            ▼ (Ducking Mode)           ▼ (None Mode)
┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
│ Tách âm bằng AI       │  │ Dìm âm lượng gốc      │  │ Không giữ lại âm      │
│ (vocal_separator)     │  │ xuống -12dB           │  │ thanh cũ (Im lặng)    │
│ => vocals.wav         │  │ => background_gain_db │  │                       │
│ => no_vocals.wav (BGM)│  │                       │  │                       │
└───────────┬───────────┘  └───────────┬───────────┘  └───────────┬───────────┘
            └──────────────────────────┼──────────────────────────┘
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │    Bước 3: Nhận dạng giọng nói (ASR)    │
                  │     Groq Whisper (Fallback sang Azure)  │
                  │ => transcript_original.json/srt         │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │    Bước 4: Dịch thuật ngữ cảnh bằng AI  │
                  │    Gemini 2.0 Flash (Fallback Llama)   │
                  │ => transcript_vi.json/srt               │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │    Bước 5: Nhận diện Nhân vật & Giới tính│
                  │    (Gemini/Llama Speaker Detection)     │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼ (Dừng nếu chọn --pause-for-speakers để map tay trên UI)
                  ┌─────────────────────────────────────────┐
                  │    Bước 6: Tổng hợp giọng đọc (TTS)     │
                  │    LucyLab / LarVoice / Vivibe (cho VI) │
                  │    Azure Neural TTS (cho JA)            │
                  │ => Điều chỉnh tốc độ tự động khớp video │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │    Bước 7: Đồng bộ & Trộn Audio (Pydub) │
                  │   Căn chỉnh chênh lệch timeline gốc & VI │
                  │     Chuẩn hóa âm lượng (LUFS -15dB)     │
                  │ => audio_vi_full.wav                    │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │     Bước 8: Kết xuất Video (FFmpeg)     │
                  │      (Tùy chọn ghi cứng phụ đề)        │
                  │ => dubbed_video.mp4                     │
                  └────────────────────┬────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
┌───────────────────────────────────────┐   ┌───────────────────────────────────────┐
│     Bước 9: SEO & Thumbnail Prompts   │   │     Bước 10: Tự động Xuất bản         │
│     Gemini tạo Tiêu đề, Mô tả, Tag     │   │     Đăng tải lên YouTube (Private)    │
│     & Prompt Midjourney vẽ Thumbnail  │   │     và Facebook Page công khai        │
│ => youtube_metadata.json / post.txt   │   │ => Trả về đường dẫn link video        │
└───────────────────────────────────────┘   └───────────────────────────────────────┘
```

---

## 💻 Công nghệ áp dụng (Technology Stack)

Hệ thống được thiết kế theo cấu trúc modular hóa bằng ngôn ngữ **Python** và tích hợp các dịch vụ đám mây tiên tiến:

*   **Bộ lõi xử lý Audio/Video**:
    *   `FFmpeg`: Trích xuất âm thanh, thay thế kênh tiếng, chuẩn hóa âm lượng theo chuẩn phát sóng và ghi phụ đề cứng (burn subtitles).
    *   `Pydub`: Cắt ghép các đoạn âm thanh, tạo khoảng lặng (silence padding) và chèn đè các tệp tin âm thanh theo timeline mili-giây.
    *   `Soundfile` & `Numpy`: Đọc/ghi các tệp WAV 16-bit PCM chất lượng cao.
*   **Bộ tách nguồn âm thanh (Vocal Separation)**:
    *   `Meta Demucs (htdemucs v4)`: Chạy trực tiếp trên PyTorch để phân tách âm thanh gốc thành giọng nói rời rạc và tệp nhạc nền/hiệu ứng tiếng động sạch bóng.
*   **Bộ nhận dạng giọng nói (ASR)**:
    *   `Groq Cloud (Whisper Large V3)`: Chạy nhận dạng siêu tốc. Hệ thống tự động nén tệp âm thanh đầu vào thành MP3 chất lượng tốt để đảm bảo dưới hạn ngạch API 25MB.
    *   `Azure Speech Service SDK`: Sử dụng làm giải pháp Fallback dự phòng chất lượng cao cho các video siêu dài cần nhận dạng liên tục (`Continuous Recognition`).
*   **Bộ dịch thuật & Xử lý ngôn ngữ (LLMs)**:
    *   `Google GenAI SDK (Gemini 2.0 Flash)`: Sử dụng dịch thuật ngữ cảnh phức tạp và tạo gợi ý metadata SEO.
    *   `Groq LLM (Llama 3.3 70B Versatile)`: Hoạt động ở chế độ JSON để fallback dịch thuật và nhận diện nhân vật nếu Gemini lỗi quota.
*   **Bộ tổng hợp giọng nói (TTS)**:
    *   **Tiếng Việt**: Tích hợp các nhà cung cấp nổi tiếng gồm **LucyLab**, **LarVoice**, **Vivibe API**, và **TikTok TTS** (hỗ trợ giọng đọc "Cô gái hoạt ngôn" `vi_vn_002` và giọng nữ tiêu chuẩn `vi_vn_001`). Hỗ trợ cả giọng đọc nam/nữ của nhiều vùng miền.
    *   **Tiếng Nhật**: Tích hợp **Azure Neural TTS** (mặc định giọng `ja-JP-KeitaNeural` và `ja-JP-NanamiNeural`) hỗ trợ giọng đọc biểu cảm chất lượng phòng thu.
*   **Trình tải video**:
    *   `yt-dlp`: Công cụ CLI hàng đầu để tải video và phụ đề từ hơn 1000 trang web.
    *   `Playwright (Chromium headless browser)`: Giả lập trình duyệt để vượt qua hệ thống bảo vệ và thu thập dữ liệu video từ Douyin (TikTok Trung Quốc).
*   **Giao diện & Web Server**:
    *   `FastAPI`: Cung cấp Web Server nhẹ, hỗ trợ xử lý nền (Background Tasks), WebSocket và API RESTful.
    *   `Uvicorn`: ASGI web server hiệu năng cao phục vụ UI cục bộ.
    *   `Vanilla HTML, JS & CSS Variables`: Thiết kế giao diện Glassmorphism độc đáo mà không cần cài thêm các framework nặng nề.

---

## 📁 Cấu trúc Thư mục Nguồn (Source Directory Structure)

```
Auto-Translade-video/
├── .env.example                # Bản mẫu khai báo API Keys và cấu hình mặc định
├── requirements.txt            # Danh sách thư viện Python phụ thuộc cần cài đặt
├── config.py                   # Module trung tâm quản lý cấu hình hệ thống và đọc .env
├── pipeline.py                 # CLI chính xử lý lồng tiếng Nhật (EN/VI -> JP)
├── pipeline_vi.py              # CLI chính xử lý lồng tiếng Việt (EN/JA/ZH -> VI)
├── batch_run.py                # Script chạy hàng loạt lồng tiếng Nhật qua Excel
├── batch_run_vi.py             # Script chạy hàng loạt lồng tiếng Việt qua Excel
├── batch_run_json.py           # Script chạy hàng loạt lồng tiếng Việt qua tệp JSON
├── run_content_gen.py          # Script chạy lại bước tạo Metadata SEO & Thumbnail cho video thành công
├── get_youtube_script.py       # Công cụ cào nhanh phụ đề (transcript) thuần từ YouTube
├── web_server.py               # Máy chủ FastAPI Web UI phục vụ giao diện người dùng
│
├── src/                        # Thư mục mã nguồn các module xử lý chi tiết
│   ├── __init__.py
│   ├── audio_extractor.py      # Trích xuất audio từ video sang WAV 16kHz Mono bằng FFmpeg
│   ├── audio_merger.py         # Ghép nối các phân đoạn audio TTS, tự động co giãn và chèn nhạc nền
│   ├── content_generator.py    # Xử lý sinh Tiêu đề, Mô tả, Hashtags và gợi ý vẽ Thumbnail qua Gemini/Llama
│   ├── downloader.py           # Tải video từ YouTube/TikTok qua yt-dlp
│   ├── downloader_douyin.py    # Giả lập Playwright tải video Douyin an toàn
│   ├── publisher.py            # Upload thành phẩm lên YouTube (OAuth2) và Facebook Page
│   ├── speaker_detector.py     # Phân tích văn bản nhận diện vai trò nhân vật và giới tính
│   ├── srt_generator.py        # Tạo file phụ đề tiêu chuẩn SRT từ dữ liệu transcript
│   ├── synthesizer.py          # Tổng hợp giọng nói tiếng Nhật bằng Azure Speech SDK
│   ├── synthesizer_vi.py       # Tổng hợp giọng nói tiếng Việt bằng LucyLab/LarVoice/Vivibe
│   ├── transcriber.py          # Nhận dạng giọng nói (ASR) bằng Groq Whisper hoặc Azure
│   ├── translate_pending.py    # Ghi nhận trạng thái dịch chờ duyệt thủ công khi API lỗi
│   ├── translator.py           # Dịch thuật thông minh (xử lý xưng hô pronoun và kiểm soát độ dài ký tự)
│   ├── utils.py                # Cấu hình log ghi chép và các tiện ích quản lý thư mục
│   └── video_merger.py         # Trộn âm thanh lồng tiếng hoàn chỉnh vào video gốc bằng FFmpeg
│
├── static/                     # Tài nguyên giao diện Web UI
│   └── index.html              # Trang giao diện chính (giao diện Glassmorphism Dark Terminal)
│
├── tests/                      # Thư mục chứa các tệp kiểm thử tự động pytest
│   ├── test_audio_merger.py
│   ├── test_config.py
│   ├── test_speaker_detector.py
│   ├── test_srt_generator.py
│   ├── test_synthesizer_vi.py
│   ├── test_translator.py
│   ├── test_vocal_separator.py
│   └── test_web_server.py
│
└── output/                     # Thư mục đầu ra mặc định (chứa các session xử lý)
```

---

## 🛠️ Cài đặt & Yêu cầu Hệ thống

### Yêu cầu tiên quyết:
1.  **Python 3.10 hoặc 3.11** (Lưu ý: Thư viện `audioop-lts` chỉ tự động kích hoạt trên Python 3.13+, khuyến nghị sử dụng Python 3.10/3.11 để có độ tương thích tốt nhất).
2.  **FFmpeg**: Cần cài đặt trên hệ điều hành và thêm vào đường dẫn hệ thống `PATH`.
    *   *Windows (PowerShell)*: `winget install FFmpeg` hoặc sử dụng `choco install ffmpeg`.
    *   *macOS (Homebrew)*: `brew install ffmpeg`
    *   *Ubuntu/Debian*: `sudo apt update && sudo apt install ffmpeg`

### Hướng dẫn Cài đặt:

```bash
# 1. Clone hoặc tải mã nguồn dự án về máy
cd Auto-Translade-video

# 2. Cài đặt các thư viện Python phụ thuộc
pip install -r requirements.txt

# 3. Khởi tạo cấu hình trình duyệt Playwright (dành cho việc tải video Douyin)
python -m playwright install chromium

# 4. Tạo tệp cấu hình môi trường từ bản mẫu
cp .env.example .env
```

---

## 🔐 Cấu hình biến môi trường (.env)

Mở tệp `.env` vừa tạo và điền các API Key tương ứng. Dưới đây là mô tả chi tiết từng biến cấu hình:

| Tên biến môi trường | Giá trị mẫu | Yêu cầu | Ý nghĩa & Vai trò trong Pipeline |
| :--- | :--- | :--- | :--- |
| `GROQ_API_KEY` | `gsk_xxxx...` | Khuyến nghị | Nhận dạng ASR siêu tốc qua Whisper v3 và Fallback dịch thuật Llama |
| `GOOGLE_API_KEY` | `AIzaSyxxxx...` | Khuyến nghị | Dịch thuật chất lượng cao (Gemini 2.0 Flash) & Sinh Metadata SEO |
| `AZURE_SPEECH_KEY` | `xxxx...` | Tùy chọn | Dùng để chạy ASR dự phòng (Fallback) và lồng tiếng Nhật (Azure TTS) |
| `AZURE_SPEECH_REGION` | `japaneast` | Tùy chọn | Khu vực đặt tài nguyên Azure Speech Service |
| `TTS_PROVIDER` | `lucylab` / `larvoice` / `tiktok` | Bắt buộc | Nhà cung cấp giọng đọc tiếng Việt chính (`lucylab`, `larvoice`, hoặc `tiktok`) |
| `VIETNAMESE_API_KEY` | `Bearer xxxx...` | Bắt buộc | Token xác thực cho LucyLab hoặc LarVoice TTS (không bắt buộc đối với `tiktok`) |
| `TIKTOK_SESSION_ID` | `sessionid_cookie` | Tùy chọn | Cookie `sessionid` từ trình duyệt sau khi đăng nhập TikTok (bắt buộc khi chọn provider là `tiktok` để tránh lỗi) |
| `VIETNAMESE_VOICEID_MALE` | `vi_vn_001` | Bắt buộc | ID giọng đọc Nam tiếng Việt mặc định (với TikTok là `vi_vn_001`) |
| `VIETNAMESE_VOICEID_FEMALE` | `vi_vn_002` | Bắt buộc | ID giọng đọc Nữ tiếng Việt mặc định (với TikTok là `vi_vn_002` - giọng Cô gái hoạt ngôn) |
| `VOICE_NARRATOR` | `vi_vn_002` | Tùy chọn | ID giọng đọc dành riêng cho người dẫn chuyện (Narrator) |
| `VOICE_CHARACTER_MAP` | `HERO:id1,VILLAIN:id2` | Tùy chọn | Bản đồ cố định gán nhãn nhân vật (chữ HOA) sang ID giọng đọc |
| `AUDIO_SLOW_FACTOR` | `0.82` | Mặc định | Tỉ lệ giảm tốc giọng Việt (0.82 nghĩa là giảm 18% để nghe tự nhiên hơn) |
| `AUDIO_TARGET_LUFS` | `-15.0` | Mặc định | Độ lớn âm thanh đích (LUFS) sau khi mix để đăng lên YouTube/FB |
| `YOUTUBE_CLIENT_SECRETS` | `client_secrets.json` | Tùy chọn | Đường dẫn tệp OAuth2 Client Secrets để đăng ký API YouTube |
| `FACEBOOK_PAGE_ID` | `1000xxxx...` | Tùy chọn | ID Fanpage Facebook cần đăng tải video lồng tiếng |
| `FACEBOOK_PAGE_TOKEN` | `EAAGxxxx...` | Tùy chọn | Page Access Token dài hạn của Facebook Graph API |

---

## 💻 Hướng dẫn Sử dụng

Dự án cung cấp 3 phương thức vận hành tùy theo nhu cầu sử dụng của bạn:

### Cách 1: Sử dụng Giao diện Web UI (Khuyến nghị)

Giao diện Web UI của dự án được thiết kế theo phong cách **Dark Terminal (Max Yinger style)**, cho phép bạn điều khiển mọi hoạt động một cách trực quan, theo dõi log telemetry thời gian thực và cấu hình giọng nói nhân vật dễ dàng.

Để khởi động máy chủ giao diện:
```bash
python web_server.py
```
Sau đó mở trình duyệt và truy cập: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.

> [!TIP]
> **Các tính năng nổi bật trên Web UI**:
> *   **Dynamic Progress Tracking**: Hiển thị tiến trình dạng các nút sơ đồ bước (Step-by-step progress bubble) tự động sáng lên khi qua các bước.
> *   **Terminal Logging Emulator**: Màn hình dòng lệnh giả lập tự động cuộn hiển thị nhật ký xử lý chi tiết.
> *   **Interactive Speaker Mapping**: Khi bật tùy chọn *Pause for Speaker*, hệ thống sẽ dừng lại ở Bước 4.5 và hiển thị danh sách các nhân vật phát hiện được trong video. Bạn có thể bấm chọn gán giọng Nam/Nữ hoặc nhập ID giọng tùy chọn rồi nhấn tiếp tục để tổng hợp.
> *   **Thành phẩm trực quan**: Phát trực tiếp video kết quả ngay trên trình duyệt, có sẵn nút sao chép Tiêu đề, Mô tả và Hashtags chuẩn SEO.

---

### Cách 2: Sử dụng dòng lệnh CLI (Dòng lệnh đơn lẻ)

Bạn có thể chạy trực tiếp pipeline thông qua terminal bằng cách gọi tệp script tương ứng.

#### 1. Lồng tiếng Việt (Hỗ trợ nguồn EN, JA, ZH sang VI):
```bash
# Chạy cơ bản từ URL (YouTube / TikTok / Douyin)
python pipeline_vi.py --url "https://www.youtube.com/watch?v=xxxx" --source-lang en --voice female

# Chạy từ tệp video cục bộ có sẵn trên máy
python pipeline_vi.py --file "C:/Videos/my_video.mp4" --source-lang zh --voice male

# Tùy chỉnh chế độ xử lý nhạc nền gốc (--bg-mode):
# 1. demucs (Mặc định): Tách âm bằng AI giữ lại nhạc nền sạch sẽ nhất (Yêu cầu CPU/GPU)
python pipeline_vi.py --url "https://..." --bg-mode demucs
# 2. duck: Giảm âm lượng giọng gốc xuống -12dB (chạy cực nhanh, giọng cũ nghe nhỏ nhỏ ở dưới)
python pipeline_vi.py --url "https://..." --bg-mode duck --bg-duck-db -15.0
# 3. none: Im lặng hoàn toàn phần nền, chỉ nghe thấy giọng đọc Việt
python pipeline_vi.py --url "https://..." --bg-mode none

# Bật tính năng nhận diện nhân vật và dừng lại để ánh xạ thủ công
python pipeline_vi.py --url "https://..." --pause-for-speakers

# Ghi cứng phụ đề tiếng Việt trực tiếp vào luồng hình ảnh của video
python pipeline_vi.py --url "https://..." --burn-subtitles

# Tự động xuất bản lên mạng xã hội ngay sau khi render xong
python pipeline_vi.py --url "https://..." --publish-youtube --publish-facebook
```

#### 2. Lồng tiếng Nhật (Hỗ trợ nguồn EN, VI sang JP):
```bash
python pipeline.py --url "https://www.youtube.com/watch?v=xxxx" --source-lang en --voice ja-JP-KeitaNeural
```

#### 3. Chạy tiếp tục (Resume) từ một thư mục đã xử lý dang dở:
Nếu pipeline bị gián đoạn (do mất mạng, hết hạn ngạch API, hoặc bạn dừng lại để sửa thủ công bản dịch), bạn có thể chạy tiếp tục mà không cần tải hay chạy ASR lại từ đầu:
```bash
python pipeline_vi.py --resume "output/VN/20260621103000_vi" --source-lang en
```

---

### Cách 3: Xử lý Hàng loạt (Batch Process)

Khi cần xử lý hàng chục video cùng lúc, bạn có thể lập danh sách và để hệ thống chạy tự động qua đêm.

#### 1. Chạy hàng loạt qua Excel (`batch_run_vi.py`):
Tạo một tệp Excel (Ví dụ `output/video_link.xlsx`) có cấu trúc như sau:
*   **Cột A (Dòng 2 trở đi)**: Link video cần lồng tiếng.
*   **Cột B**: Trạng thái (để trống). Hệ thống sẽ tự ghi `SUCCESS` hoặc `FAILED: <lỗi>` sau khi xử lý.
*   **Cột C**: Tên thư mục kết quả.

Chạy lệnh:
```bash
python batch_run_vi.py --excel "output/video_link.xlsx" --voice female
```

#### 2. Chạy hàng loạt qua tệp JSON (`batch_run_json.py`):
Tạo file `list_video.json` dạng:
```json
[
  {
    "id": 1,
    "video_url": "https://www.youtube.com/watch?v=video1",
    "voice_type": "female",
    "status": "waiting"
  },
  {
    "id": 2,
    "video_url": "https://www.youtube.com/watch?v=video2",
    "voice_type": "male",
    "status": "waiting"
  }
]
```
Chạy lệnh:
```bash
python batch_run_json.py --json "list_video.json"
```
Hệ thống sẽ cập nhật trạng thái trực tiếp vào tệp JSON trên sau mỗi lần xử lý xong một video.

---

### Các công cụ phụ trợ hữu ích

#### 1. Trích xuất văn bản phụ đề YouTube siêu tốc (`get_youtube_script.py`)
Công cụ giúp bạn tải nhanh transcript dạng văn bản thuần từ bất kỳ link YouTube nào. Script sẽ cố gắng gọi API lấy caption sẵn có trước, nếu không được mới tải qua `yt-dlp`.
```bash
# Tải script video lưu ra file text mặc định
python get_youtube_script.py "https://www.youtube.com/watch?v=xxxx" --lang vi,en

# Lưu ra file chỉ định
python get_youtube_script.py "https://..." --output "scripts/content.txt"
```

#### 2. Tạo lại thông tin đăng bài SEO cho video thành công (`run_content_gen.py`)
Nếu trong lúc chạy pipeline chính, Google API bị lỗi khiến video không sinh được metadata hoặc ảnh Thumbnail, bạn không cần chạy lại toàn bộ video. Chỉ cần chạy lệnh này để quét danh sách video thành công trong `list_video.json` và bổ sung file post SEO:
```bash
python run_content_gen.py
```

---

## 📁 Cấu trúc Thư mục Đầu ra (Output Structure)

Mỗi phiên làm việc (session) lồng tiếng Việt sẽ được lưu trữ trong một thư mục riêng biệt đặt tên theo định dạng `<thời_gian>_vi` nằm trong `output/VN/`:

```
output/VN/20260621103000_vi/
├── input.mp4                       # Video gốc được tải về từ URL hoặc copy từ local
├── original_audio.wav              # File âm thanh gốc được trích xuất từ video (16kHz WAV)
├── vocals.wav                      # Tệp giọng nói gốc (chỉ xuất hiện khi dùng --bg-mode demucs)
├── no_vocals.wav                   # Nhạc nền và âm thanh hiệu ứng sạch (chỉ khi dùng --bg-mode demucs)
├── transcript_original.json        # File lưu kết quả nhận dạng giọng nói ASR kèm timestamps
├── transcript_original.srt         # Phụ đề gốc xuất ra định dạng SRT chuẩn chỉnh
├── transcript_vi.json              # Bản dịch tiếng Việt của từng đoạn và thông tin nhân vật
├── transcript_vi.srt               # Phụ đề tiếng Việt hoàn chỉnh dạng SRT
├── timing_guide.json               # Báo cáo so sánh chênh lệch thời lượng câu gốc và câu dịch Việt
├── fit_adjustments.json            # Ghi nhận điều chỉnh vị trí âm thanh để chống đè thoại
├── voice_character_map.json        # Bản đồ ánh xạ nhân vật sang ID giọng đọc sử dụng
│
├── segments/                       # Chứa các file audio lồng tiếng Việt gốc cho từng phân đoạn
│   ├── seg_001.wav
│   └── seg_002.wav
├── segments_fit/                   # Audio phân đoạn đã được tinh chỉnh thời gian để không đè nhau
│
├── audio_vi_full.wav               # Audio lồng tiếng Việt hoàn chỉnh sau khi trộn với nhạc nền (no_vocals)
├── dubbed_video.mp4                # Video thành phẩm cuối cùng đã được ghép tiếng Việt
├── thumbnail_prompts.txt           # File chứa các prompt đề xuất vẽ Thumbnail bằng Midjourney / DALL-E
├── youtube_metadata.json           # File lưu cấu trúc JSON Tiêu đề, Mô tả, Hashtags đề xuất SEO
├── youtube_post.txt                # File mẫu nội dung đăng bài bao gồm Tiêu đề, Mô tả và Hashtags
└── report.json                     # Báo cáo thông số: thời gian chạy, tỉ lệ chỉnh tốc độ thoại, link publish...
```

---

## 🎬 Quy trình Hậu kỳ với phần mềm Edit Video (CapCut)

Mặc dù video đầu ra `dubbed_video.mp4` đã sẵn sàng để đăng tải ngay lập tức, đối với các sản phẩm truyền hình chất lượng cao, chúng tôi khuyên bạn nên đưa các thành phần trong thư mục output vào phần mềm chỉnh sửa chuyên nghiệp (như CapCut, Premiere) để tối ưu:

```
1. Khởi tạo một dự án mới trong CapCut.
2. Import tệp tin video gốc (hoặc input.mp4) làm luồng hình ảnh.
3. Import tệp phụ đề dịch tiếng Việt (transcript_vi.srt) => tự động hiển thị text overlay.
4. Import tệp audio hoàn chỉnh (audio_vi_full.wav) => đặt vào luồng tiếng chính và tắt tiếng (mute) video gốc.
5. Tiến hành căn chỉnh thủ công:
   - Nếu có đoạn nào giọng đọc Việt bị nhanh quá, bạn có thể kéo giãn nhẹ hoặc dịch chuyển tệp tin WAV phân đoạn tương ứng nằm trong thư mục `segments/` để khớp khớp cử chỉ môi của nhân vật tốt nhất.
   - Thêm các hiệu ứng chuyển cảnh, bộ lọc hoặc điều chỉnh phông chữ phụ đề theo nhận diện thương hiệu của bạn.
6. Kết xuất video thành phẩm cuối cùng.
```

---

## 🧪 Chạy Kiểm thử (Unit Tests)

Dự án đi kèm bộ unit tests đầy đủ bao phủ từ khâu cấu hình, xử lý ghép nhạc, dịch thuật, cho đến giả lập web server. Bạn có thể sử dụng thư viện `pytest` để kiểm tra độ tin cậy của mã nguồn:

```bash
# Chạy toàn bộ các test case có trong thư mục tests
python -m pytest -v
```

---

## 💰 Ước tính Chi phí Hoạt động

Nhờ cơ chế sử dụng API hiệu quả và tận dụng tối đa gói miễn phí của các nhà cung cấp, chi phí vận hành hệ thống ở mức siêu rẻ.

### Cho 1 video thời lượng 10 phút (Khoảng 2000 từ thoại):

| Phân đoạn dịch vụ | Mức sử dụng ước tính | Chi phí trên Gói Standard |
| :--- | :--- | :--- |
| **Azure Speech ASR** | 10 phút nhận dạng | **~$0.16** (Miễn phí 5 giờ/tháng trên gói F0) |
| **Gemini 2.0 Flash** | ~3,000 tokens đầu vào + đầu ra | **~$0.005** (Thoải mái sử dụng hạn ngạch free) |
| **LucyLab / LarVoice TTS** | ~5,000 ký tự tiếng Việt | **~$0.20 - $0.35** (Tùy theo bảng giá API) |
| **Tổng chi phí** | | **~5.000đ - 10.000đ / video 10 phút** |

---

## ⚠️ Hạn chế hiện tại & Lưu ý pháp lý

### Hạn chế kỹ thuật:
*   **Vấn đề độ dài dịch thuật**: Tiếng Việt thường dài hơn tiếng Anh khoảng 20-30% khi phát âm cùng một nội dung. Dù hệ thống đã tự động tăng tốc đọc (tối đa 1.3x) thông qua SSML prosody rate và ffmpeg tempo, ở các phân đoạn hội thoại quá dồn dập, âm thanh lồng tiếng vẫn có khả năng bị tràn qua timeline kế tiếp. Bạn nên dùng tùy chọn `--pause-for-speakers` để kiểm soát văn bản dịch ngắn hơn hoặc chỉnh sửa thủ công timeline trong CapCut.
*   **Chất lượng âm thanh tách Demucs**: AI tách âm nền yêu cầu cấu hình máy tính có RAM từ 8GB trở lên. Quá trình xử lý tách âm trên CPU có thể mất từ 3-8 phút tùy thuộc vào độ dài video.

### Lưu ý pháp lý & Bản quyền:
*   Công cụ `yt-dlp` được tích hợp chỉ phục vụ mục đích tải nội dung để chuyển ngữ cá nhân. Vui lòng đảm bảo bạn sở hữu quyền sở hữu trí tuệ hoặc được sự đồng ý của tác giả video gốc trước khi dịch và xuất bản lại.
*   Không sử dụng tính năng giả lập giọng nói (TTS) để tạo ra các nội dung mạo danh, lừa đảo hoặc vi phạm pháp luật hiện hành.
*   Tuyệt đối **không commit tệp tin `.env`** chứa các API Keys cá nhân lên các kho lưu trữ công khai như GitHub.

---

## 📄 Bản quyền (License)

Mã nguồn dự án được phân phối và bảo hộ dưới giấy phép bản quyền **MIT License**.
