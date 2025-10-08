# Multi-stage Docker build for YouTube Download Service
# Stage 1: Builder - Install build dependencies and compile requirements
FROM python:3.11-slim-bullseye AS builder

# Set build arguments for security
ARG DEBIAN_FRONTEND=noninteractive
ARG BUILD_USER_UID=1000
ARG BUILD_USER_GID=1000

# Create build user for security
RUN groupadd -g ${BUILD_USER_GID} builduser && \
    useradd -u ${BUILD_USER_UID} -g ${BUILD_USER_GID} -m -s /bin/bash builduser

# Install build dependencies with security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    pkg-config \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create virtual environment with proper ownership
RUN python -m venv /opt/venv && \
    chown -R builduser:builduser /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Switch to build user
USER builduser

# Copy requirements and install Python dependencies
COPY --chown=builduser:builduser requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime - Create final image with minimal dependencies
FROM python:3.11-slim-bullseye AS runtime

# Set build arguments for security
ARG DEBIAN_FRONTEND=noninteractive
ARG APP_USER_UID=1001
ARG APP_USER_GID=1001

# Security: Install runtime system dependencies with security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    wget \
    ca-certificates \
    dumb-init \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && rm -rf /tmp/* /var/tmp/*

# Security: Create non-root user and group with specific UID/GID
RUN groupadd -g ${APP_USER_GID} ytdl && \
    useradd -u ${APP_USER_UID} -g ${APP_USER_GID} -r -d /opt/ytdl_service -s /sbin/nologin ytdl

# Security: Remove unnecessary packages and clean up
RUN apt-get autoremove -y && \
    apt-get autoclean

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /opt/ytdl_service

# Security: Create necessary directories with minimal permissions
RUN mkdir -p /opt/ytdl_service/downloads \
             /opt/ytdl_service/app \
             /opt/ytdl_service/config \
             /var/log \
             /tmp/ytdl \
    && chown -R ytdl:ytdl /opt/ytdl_service \
    && chown -R ytdl:ytdl /var/log \
    && chown -R ytdl:ytdl /tmp/ytdl \
    && chmod 750 /opt/ytdl_service \
    && chmod 755 /opt/ytdl_service/downloads \
    && chmod 750 /opt/ytdl_service/app \
    && chmod 700 /opt/ytdl_service/config \
    && chmod 755 /var/log \
    && chmod 700 /tmp/ytdl

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

# Copy entrypoint, health check, and security scripts with secure permissions
COPY --chown=ytdl:ytdl entrypoint.sh /opt/ytdl_service/
COPY --chown=ytdl:ytdl health_check.sh /opt/ytdl_service/
COPY --chown=ytdl:ytdl security-config.sh /opt/ytdl_service/
RUN chmod 750 /opt/ytdl_service/entrypoint.sh && \
    chmod 750 /opt/ytdl_service/health_check.sh && \
    chmod 750 /opt/ytdl_service/security-config.sh

# Security: Switch to non-root user early
USER ytdl

# Security: Set umask for restrictive file creation
RUN echo "umask 027" >> /opt/ytdl_service/.bashrc

# Security: Set secure environment variables
ENV PYTHONPATH="/opt/ytdl_service/app:$PYTHONPATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DOWNLOADS_DIR="/opt/ytdl_service/downloads" \
    LOGS_DIR="/var/log" \
    API_KEY_FILE="/opt/ytdl_service/config/api_key.txt" \
    PORT=8000 \
    TMPDIR="/tmp/ytdl"

# Security: Expose only necessary port
EXPOSE 8000

# Security: Add labels for metadata and security scanning
LABEL maintainer="ytdl-service" \
      version="1.0" \
      description="YouTube Download Service - Security Hardened" \
      security.scan="enabled" \
      security.non-root="true" \
      security.readonly-rootfs="partial"

# Health check using our comprehensive health check script
HEALTHCHECK --interval=30s --timeout=15s --start-period=10s --retries=3 \
    CMD /opt/ytdl_service/health_check.sh --quick || exit 1

# Security: Use dumb-init as PID 1 for proper signal handling
ENTRYPOINT ["/usr/bin/dumb-init", "--", "/opt/ytdl_service/entrypoint.sh"]

# Default command
CMD ["python", "/opt/ytdl_service/app/download_service.py"]