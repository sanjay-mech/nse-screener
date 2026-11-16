# Multi-Stage / Production Dockerfile for NSE Breakout Screener
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Kolkata

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Create non-root application user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Set ownership to appuser
RUN chown -R appuser:appuser /app

USER appuser

# Expose web dashboard port
EXPOSE 8000

# Default command runs the unified web dashboard & engine
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
