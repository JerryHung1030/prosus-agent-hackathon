# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy backend as a proper Python package under /app/backend
COPY backend/ /app/backend/
# Also copy the agent src package so imports like `from src.main import ...` work
COPY src/ /app/src/

EXPOSE 8000

# Run the app using the package module path so relative imports resolve
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
