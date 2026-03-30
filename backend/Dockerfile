FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential \
    libxcb1 libx11-6 libxext6 libxrender1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install deps first (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
