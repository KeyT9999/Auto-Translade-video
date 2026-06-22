# Hướng dẫn lấy và cấu hình file `.env` cho dự án

Tài liệu này hướng dẫn chi tiết cách tạo, cấu hình và lấy các API Key cần thiết để chạy dự án **Auto-Translade-video**.

---

## 1. Cách thiết lập ban đầu (Bỏ file `.env` vào dự án)

1. Trong thư mục gốc của dự án, bạn sẽ thấy một file mẫu có tên là `.env.example`.
2. Hãy sao chép (copy) file này và đổi tên thành `.env`.
   - *Trên Windows Explorer:* Click chuột phải vào `.env.example` -> **Copy**, sau đó **Paste** và đổi tên thành `.env`.
   - *Hoặc dùng dòng lệnh (Terminal/PowerShell):*
     ```powershell
     cp .env.example .env
     ```
3. Mở file `.env` vừa tạo bằng VS Code, Notepad hoặc bất kỳ trình soạn thảo mã nguồn nào để bắt đầu điền các API Key bên dưới.

---

## 2. Hướng dẫn chi tiết cách lấy các API Key

Dưới đây là các API Key quan trọng nhất cần cấu hình để chạy được các tính năng của pipeline dịch thuật và lồng tiếng.

### 🔑 A. Groq API Key (Nhận dạng giọng nói ASR bằng Whisper & Dịch dự phòng)
*   **Chức năng:** Dùng để chuyển đổi giọng nói trong video gốc thành văn bản (chạy Whisper Large V3 siêu tốc) và chạy mô hình Llama dự phòng.
*   **Cách lấy:**
    1. Truy cập trang web: [Groq Console](https://console.groq.com/)
    2. Đăng ký tài khoản (hỗ trợ liên kết tài khoản Google).
    3. Chọn mục **API Keys** ở menu bên trái.
    4. Bấm **Create API Key**, đặt tên gợi nhớ (ví dụ: `Auto-Translate`) và sao chép mã nhận được.
    5. Dán vào dòng:
       ```env
       GROQ_API_KEY=gsk_your_key_here
       ```

### 🔑 B. Google API Key (Dịch thuật chính bằng Gemini 2.0 Flash)
*   **Chức năng:** Dịch thuật ngữ cảnh, phân tích xưng hô và sinh tiêu đề/mô tả chuẩn SEO.
*   **Cách lấy:**
    1. Truy cập: [Google AI Studio](https://aistudio.google.com/)
    2. Đăng nhập bằng tài khoản Google.
    3. Bấm nút **Get API key** ở góc trên bên trái.
    4. Chọn **Create API Key** -> Chọn project hiện có hoặc tạo mới -> Click **Create API Key in existing project**.
    5. Sao chép API Key và dán vào dòng:
       ```env
       GOOGLE_API_KEY=your_gemini_api_key_here
       ```
    6. Nhớ kích hoạt:
       ```env
       GEMINI_ENABLED=true
       ```

### 🔑 C. DeepSeek API Key (Mô hình dịch thuật chất lượng cao)
*   **Chức năng:** Dùng làm dịch thuật chính hoặc thay thế khi Gemini bị giới hạn hạn ngạch (quota limit).
*   **Cách lấy:**
    1. Truy cập: [DeepSeek Platform](https://platform.deepseek.com/)
    2. Đăng ký/Đăng nhập tài khoản.
    3. Vào mục **API Keys** -> Bấm **Create API Key**.
    4. Sao chép key và dán vào dòng:
       ```env
       DEEPSEEK_API_KEY=sk-xxxx...
       ```

### 🔑 D. Vietnamese TTS API Key (LucyLab hoặc LarVoice - Lồng tiếng Việt)
*   **Chức năng:** Chuyển đổi văn bản tiếng Việt đã dịch thành giọng nói tự nhiên chất lượng cao.
*   **Cách lấy (Ví dụ với LucyLab):**
    1. Truy cập trang chủ nhà cung cấp: [LucyLab](https://lucylab.io/) hoặc hệ thống TTS bạn đăng ký.
    2. Đăng ký tài khoản và nạp tiền/đăng ký gói dịch vụ.
    3. Vào mục cấu hình API/Token để lấy Access Token.
    4. Cập nhật các biến sau trong `.env`:
       ```env
       TTS_PROVIDER=lucylab  # Hoặc larvoice tùy dịch vụ bạn sử dụng
       VIETNAMESE_API_KEY=Bearer your_token_here
       VIETNAMESE_VOICEID_MALE=id_giọng_nam_của_bạn
       VIETNAMESE_VOICEID_FEMALE=id_giọng_nữ_của_bạn
       ```

### 🔑 E. Azure Speech Service API (Cho lồng tiếng Nhật / Nhận diện ASR dự phòng)
*   **Chức năng:** Sử dụng công nghệ TTS cao cấp của Microsoft Azure cho tiếng Nhật và nhận diện âm thanh video siêu dài.
*   **Cách lấy:**
    1. Truy cập [Azure Portal](https://portal.azure.com/).
    2. Tạo một tài nguyên **Speech** thuộc **Cognitive Services**.
    3. Vào mục **Keys and Endpoint** để sao chép **KEY 1** và **Location/Region**.
    4. Dán vào `.env`:
       ```env
       AZURE_SPEECH_KEY=your_key_here
       AZURE_SPEECH_REGION=japaneast  # Hoặc khu vực tương ứng bạn tạo
       ```

---

## 3. Lưu ý quan trọng về bảo mật ⚠️

> [!WARNING]
> **Không bao giờ chia sẻ công khai file `.env` lên GitHub/GitLab!**
>
> File `.env` chứa các khóa API cá nhân có thể mất tiền hoặc bị lợi dụng nếu lộ ra ngoài. Dự án đã tự động thêm `.env` vào file `.gitignore` để tránh bị đẩy lên Git. Hãy giữ file này an toàn trên máy tính cá nhân của bạn.
