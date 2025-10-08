# Multi-stage Docker build for YouTube Download Service
# Stage 1: Builder - Install build dependencies and compile requirements
FROM python:3.11-slim-bullseye AS builder

# Set build arguments
ARG DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime - Create final image with minimal dependencies
FROM python:3.11-slim-bullseye AS runtime

# Set build arguments
ARG DEBIAN_FRONTEND=noninteractive

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user and group
RUN groupadd -r ytdl && useradd -r -g ytdl -d /opt/ytdl_service -s /bin/bash ytdl

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /opt/ytdl_service

# Create necessary directories with proper permissions
RUN mkdir -p /opt/ytdl_service/downloads \
             /opt/ytdl_service/app \
             /opt/ytdl_service/config \
             /var/log \
    && chown -R ytdl:ytdl /opt/ytdl_service \
    && chown -R ytdl:ytdl /var/log \
    && chmod 755 /opt/ytdl_service/downloads \
    && chmod 755 /var/log

# Copy application code
COPY --chown=ytdl:ytdl download_service.py /opt/ytdl_service/app/
COPY --chown=ytdl:ytdl video_downloader.py /opt/ytdl_service/app/

# Copy all Python files to ensure we get any additional modules
COPY --chown=ytdl:ytdl *.py /opt/ytdl_service/app/

# Copy modules directory if it exists (for Telegram bot functionality)
# Create empty modules directory to prevent import errors
RUN mkdir -p /opt/ytdl_service/app/modules && \
    touch /opt/ytdl_service/app/modules/__init__.py && \
    chown -R ytdl:ytdl /opt/ytdl_service/app/modules

# Copy entrypoint script
COPY --chown=ytdl:ytdl entrypoint.sh /opt/ytdl_service/
RUN chmod +x /opt/ytdl_service/entrypoint.sh

# Switch to non-root user
USER ytdl

# Set environment variables
ENV PYTHONPATH="/opt/ytdl_service/app:$PYTHONPATH" \
    PYTHONUNBUFFERED=1 \
    DOWNLOADS_DIR="/opt/ytdl_service/downloads" \
    LOGS_DIR="/var/log" \
    API_KEY_FILE="/opt/ytdl_service/api_key.txt" \
    PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Set entrypoint
ENTRYPOINT ["/opt/ytdl_service/entrypoint.sh"]

# Default command
CMD ["python", "/opt/ytdl_service/app/download_service.py"]