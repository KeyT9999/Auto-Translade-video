FROM python:3.10-slim

# Cài đặt các thư viện hệ thống cần thiết (FFmpeg, git, curl, build tools)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập thư mục làm việc
WORKDIR /app

# Tối ưu hóa dung lượng: Cài đặt PyTorch phiên bản CPU trước để tránh tải bản CUDA nặng (>2GB)
# (Demucs yêu cầu PyTorch, cài bản CPU sẽ giúp giảm dung lượng Docker Image xuống đáng kể)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Sao chép file requirements và cài đặt các thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cài đặt Playwright và các thư viện hệ thống cần thiết để chạy trình duyệt Chromium (dùng cho Douyin)
RUN playwright install chromium --with-deps

# Tạo sẵn các thư mục cần thiết và phân quyền (Đảm bảo chạy được trên cả Hugging Face Spaces chạy non-root)
RUN mkdir -p /app/output /app/static /app/voices && chmod -R 777 /app

# Sao chép toàn bộ mã nguồn vào container
COPY . .

# Đảm bảo phân quyền ghi cho toàn bộ thư mục (cho phép lưu video đầu ra)
RUN chmod -R 777 /app

# Mở cổng port của FastAPI
EXPOSE 8000

# Khai báo các biến môi trường mặc định
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Khởi chạy ứng dụng web FastAPI
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "8000"]
