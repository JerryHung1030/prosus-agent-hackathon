# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

# ----- System deps: build tools, Chrome runtime libs, fonts -----
RUN apt-get update && apt-get install -y --no-install-recommends \
    # base tools
    wget gnupg ca-certificates unzip curl \
    build-essential libffi-dev libssl-dev \
    # Chrome runtime libraries
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
    libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 \
    libgtk-3-0 libnss3 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 \
    libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 libxrandr2 \
    libxrender1 libxtst6 \
    # fonts so screenshots render text properly
    fonts-liberation fonts-noto-color-emoji \
 && rm -rf /var/lib/apt/lists/*

# ----- Install Google Chrome Stable (without deprecated apt-key) -----
RUN wget -qO /usr/share/keyrings/google-linux.gpg https://dl.google.com/linux/linux_signing_key.pub && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# ----- Python deps (cache-friendly) -----
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# ----- Application code -----
# Copy backend as a proper Python package under /app/backend
COPY backend/ /app/backend/
# Also copy the agent src package so imports like `from src.main import ...` work
COPY src/ /app/src/

# Optional: run as non-root (safer; Chrome sandbox behaves better)
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Helpful for Selenium to find Chrome
ENV CHROME_BIN=/usr/bin/google-chrome

EXPOSE 8000

# Run the app using the package module path so relative imports resolve
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
