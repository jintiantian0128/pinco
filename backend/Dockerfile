FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（部分 Python 包需要编译）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 云托管容器需要监听 0.0.0.0，端口用环境变量 PORT（云托管默认注入 80）
ENV PORT=80
EXPOSE 80

# 生产环境：去掉 --reload，用 1 个 worker（云托管免费额度下足够）
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
