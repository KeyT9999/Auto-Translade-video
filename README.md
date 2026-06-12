# Auto-Translade-video

Hệ thống tự động lồng tiếng video (YouTube / TikTok / Douyin / file local) sang **tiếng Việt** hoặc **tiếng Nhật**, giữ nguyên nhạc nền/hiệu ứng âm thanh gốc và tự động xuất bản (YouTube/Facebook) kèm tối ưu hóa SEO bằng AI.

---

## 🚀 Tính năng nổi bật mới

1. **Giao diện Web UI Hiện đại (Premium Glassmorphism):**
   - Điều khiển toàn bộ pipeline trực quan trên giao diện Web tuyệt đẹp (Dark Mode, hiệu ứng phát sáng Neon).
   - Theo dõi tiến trình thời gian thực bằng thanh Progress Bar và màn hình Terminal mô phỏng hiển thị logs chi tiết.
   - Phát trực tiếp video thành phẩm ngay trên web, sao chép nhanh đề xuất tiêu đề, mô tả và hashtag SEO.

2. **Quy trình ASR Tối ưu với Groq Whisper:**
   - Sử dụng **Groq Whisper Large V3** làm công cụ ASR chính để nhận dạng giọng nói siêu tốc và chính xác. Tự động nén audio sang MP3 để đảm bảo dung lượng gửi lên API luôn dưới 25MB.
   - Tự động **fallback** sang **Azure Speech ASR** nếu cấu hình Groq bị thiếu hoặc lỗi.

3. **Dịch thuật Tự động & Cơ chế Fallback Thông minh:**
   - **Tự động 100%:** Dịch các phân đoạn transcript sang tiếng Việt sử dụng **Google Gemini 2.0 Flash** với prompt tối ưu thời gian (duration-aware) và xưng hô tự nhiên.
   - **Tự động Fallback:** Nếu Gemini bị quá tải/hết quota (lỗi 429), hệ thống tự động chuyển sang gọi **Llama 3.3 70B** trên Groq ở chế độ JSON để hoàn thành bản dịch mà không làm gián đoạn pipeline.
   - Chỉ dừng lại dịch thủ công (`TRANSLATE_PENDING.txt`) nếu cả hai API trên đều gặp sự cố.

4. **Tự động Đăng tải & Phát hành (Auto-Publishing):**
   - Tự động đăng tải video thành phẩm lên **YouTube** (qua OAuth2 xác thực) và **Facebook Page** (qua Facebook Graph API).
   - Tự động tạo Metadata đề xuất tối ưu SEO (Tiêu đề, Mô tả, Hashtags) và gợi ý prompt vẽ Thumbnail thông qua Gemini.

---

## 🛠️ Yêu cầu hệ thống & Cài đặt

- Python 3.10+
- `ffmpeg` được cấu hình trong `PATH` hệ thống.
- Các API Keys cần thiết (khai báo trong `.env`).

### Hướng dẫn cài đặt:

```bash
# 1. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt

# 2. Cài đặt trình duyệt Playwright (cho việc download Douyin)
python -m playwright install chromium

# 3. Sao chép và cấu hình API Keys
cp .env.example .env
```

Sau khi copy `.env`, bạn hãy mở file lên và điền các API Keys tương ứng (như `GROQ_API_KEY`, `GOOGLE_API_KEY`, `VIETNAMESE_API_KEY` cho LucyLab/Vivibe TTS, v.v.).

---

## 💻 Hướng dẫn Sử dụng

### Cách 1: Sử dụng Giao diện Web UI (Khuyến khích)

Khởi động máy chủ Web UI cục bộ:
```bash
python web_server.py
```
Sau đó, truy cập: **[http://127.0.0.1:8000](http://127.0.0.1:8000)** bằng trình duyệt để bắt đầu cấu hình và theo dõi tiến trình lồng tiếng.

---

### Cách 2: Sử dụng dòng lệnh CLI (Command Line)

#### 1. Chạy lồng tiếng Việt (EN/JA/ZH ➔ VI):
```bash
# Lồng tiếng từ URL (YouTube/TikTok/Douyin)
python pipeline_vi.py --url "https://www.douyin.com/..." --source-lang zh --voice female

# Lồng tiếng từ file video cục bộ
python pipeline_vi.py --file "C:/path/to/video.mp4" --source-lang en --voice male

# Tùy chọn xử lý nhạc nền (bg-mode):
python pipeline_vi.py --url ... --bg-mode demucs     # [Mặc định] Dùng AI Demucs tách và giữ nhạc nền gốc sạch sẽ
python pipeline_vi.py --url ... --bg-mode duck       # Nhanh hơn, dìm âm lượng âm thanh gốc xuống -12dB (hoặc tùy chỉnh qua --bg-duck-db)
python pipeline_vi.py --url ... --bg-mode none       # Không giữ lại nhạc nền (âm thanh tĩnh lặng hoàn toàn)

# Tự động xuất bản lên mạng xã hội sau khi render xong:
python pipeline_vi.py --url ... --publish-youtube --publish-facebook
```

#### 2. Chạy lồng tiếng Nhật (EN/ZH ➔ JP):
```bash
python pipeline.py --url "https://..." --source-lang en --voice ja-JP-KeitaNeural
```

#### 3. Chạy tiếp tục (Resume) từ một thư mục đã xử lý:
```bash
python pipeline_vi.py --resume "output/VN/20260612130000_vi" --file "C:/path/to/video.mp4"
```

#### 4. Chạy Batch (Xử lý hàng loạt):
```bash
python batch_run_vi.py --excel output/video_link.xlsx    # Lồng tiếng Việt từ danh sách Excel
python batch_run_json.py --json list_video.json         # Lồng tiếng Việt từ danh sách JSON
python batch_run.py --excel output/video_link.xlsx      # Lồng tiếng Nhật từ danh sách Excel
```

---

## 📁 Cấu trúc Thư mục Output

Mỗi phiên làm việc (session) sẽ sinh ra một thư mục riêng trong `output/VN/` với cấu trúc như sau:

```
output/VN/20260612130000_vi/
├── Douyin_xxxx.mp4                 # Video gốc tải về
├── original_audio.wav              # Audio gốc được tách từ video
├── no_vocals.wav                   # Nhạc nền & SFX gốc (chỉ khi dùng --bg-mode demucs)
├── vocals.wav                      # Giọng nói gốc tách rời (chỉ khi dùng --bg-mode demucs)
├── transcript_original.json        # Dữ liệu ASR (Groq Whisper) gốc kèm timestamp
├── transcript_original.srt         # Phụ đề gốc dạng SRT
├── transcript_vi.json              # Dữ liệu dịch sang tiếng Việt (Gemini / Llama fallback)
├── transcript_vi.srt               # Phụ đề tiếng Việt dạng SRT
├── segments/                       # Thư mục lưu các file audio TTS (.wav) cho từng phân đoạn
│   ├── seg_001.wav
│   └── seg_002.wav
├── segments_fit/                   # Các file audio phân đoạn sau khi khớp timeline (tăng/giảm tốc)
├── audio_vi_full.wav               # Audio lồng tiếng Việt hoàn chỉnh sau khi mix với nhạc nền
├── dubbed_video.mp4                # Video thành phẩm lồng tiếng Việt cuối cùng
├── yt_metadata.json                # Tiêu đề, Mô tả, Hashtag đề xuất SEO & Prompt Thumbnail
├── report.json                     # Báo cáo thống kê tiến trình (thời gian chạy, tỉ lệ chỉnh tốc...)
└── timing_guide.json               # Chi tiết chênh lệch thời lượng giữa tiếng Việt và tiếng gốc
```

---

## 🧪 Chạy Kiểm thử (Unit Tests)

Dự án sử dụng thư viện `pytest` để kiểm tra độ tin cậy của các cấu phần. Để chạy kiểm thử, dùng lệnh:

```bash
python -m pytest
```

---

## 📄 Bản quyền (License)

Mã nguồn được phân phối dưới giấy phép **MIT**.
