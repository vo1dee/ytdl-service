# Design Document

## Overview

This design document outlines the containerization strategy for the YouTube Download Service using Docker. The service consists of a FastAPI backend (`download_service.py`) that handles video downloads using yt-dlp, and a Telegram bot interface (`video_downloader.py`). The containerization will provide consistent deployment, dependency management, and scalability.

## Architecture

### Container Architecture

The system will use a multi-stage Docker build approach with the following components:

```
┌─────────────────────────────────────────┐
│              Docker Container            │
├─────────────────────────────────────────┤
│  Application Layer                      │
│  ├─ FastAPI Service (download_service.py)│
│  ├─ Telegram Bot (video_downloader.py)  │
│  └─ yt-dlp + dependencies              │
├─────────────────────────────────────────┤
│  System Layer                          │
│  ├─ Python 3.11 Runtime               │
│  ├─ FFmpeg                            │
│  └─ System utilities                  │
├─────────────────────────────────────────┤
│  Volume Mounts                         │
│  ├─ /opt/ytdl_service/downloads       │
│  ├─ /var/log                          │
│  └─ /opt/ytdl_service/api_key.txt     │
└─────────────────────────────────────────┘
```

### Base Image Selection

- **Base Image**: `python:3.11-slim-bullseye`
- **Rationale**: 
  - Provides Python 3.11 compatibility required by the application
  - Slim variant reduces image size and attack surface
  - Debian-based for better package availability (FFmpeg)
  - Stable and well-maintained

### Multi-Stage Build Strategy

1. **Builder Stage**: Install build dependencies and compile requirements
2. **Runtime Stage**: Copy only necessary artifacts and runtime dependencies

## Components and Interfaces

### 1. Application Components

#### FastAPI Service
- **Port**: 8000 (configurable via environment)
- **Health Check**: `/health` endpoint
- **API Authentication**: X-API-Key header
- **File Serving**: `/files/{filename}` endpoint

#### Telegram Bot (Optional)
- **Integration**: Can run alongside FastAPI or separately
- **Dependencies**: Requires Telegram bot token
- **Communication**: Uses FastAPI service for downloads

#### yt-dlp Integration
- **Version**: Latest stable (2025.5.22 from requirements.txt)
- **Dependencies**: FFmpeg for video processing
- **Configuration**: Platform-specific optimizations for iOS compatibility

### 2. Volume Management

#### Downloads Volume
```
Host Path: ./downloads (or custom)
Container Path: /opt/ytdl_service/downloads
Purpose: Persistent storage for downloaded videos
Permissions: Read/Write for application user
```

#### Logs Volume
```
Host Path: ./logs (or custom)
Container Path: /var/log
Purpose: Application and system logs
Permissions: Read/Write for application user
```

#### Configuration Volume (Optional)
```
Host Path: ./config
Container Path: /opt/ytdl_service
Purpose: API key and configuration files
Permissions: Read/Write for application user
```

### 3. Network Configuration

#### Port Mapping
- **FastAPI**: 8000 (internal) → configurable (external)
- **Health Check**: Same port as FastAPI
- **No additional ports required**

#### Service Discovery
- **Internal**: Container name resolution
- **External**: Host port mapping
- **Load Balancing**: Multiple container support

## Data Models

### Environment Variables

```yaml
# Required Configuration
YTDL_SERVICE_URL: "http://localhost:8000"  # Service URL for bot communication
YTDL_SERVICE_API_KEY: "auto-generated"     # API authentication key

# Optional Configuration
YTDL_MAX_RETRIES: "3"                      # Download retry attempts
YTDL_RETRY_DELAY: "1"                      # Delay between retries (seconds)
PORT: "8000"                               # FastAPI service port

# Telegram Bot (if used)
TELEGRAM_BOT_TOKEN: ""                     # Telegram bot token
TELEGRAM_ERROR_CHAT_ID: ""                 # Error reporting chat

# Advanced Configuration
DOWNLOADS_DIR: "/opt/ytdl_service/downloads"
LOGS_DIR: "/var/log"
API_KEY_FILE: "/opt/ytdl_service/api_key.txt"
```

### File System Structure

```
/opt/ytdl_service/
├── downloads/          # Downloaded video files (volume)
├── api_key.txt        # Generated API key (volume/config)
├── app/               # Application code
│   ├── download_service.py
│   ├── video_downloader.py
│   └── modules/       # Supporting modules
└── logs/              # Application logs (volume)
```

### Docker Compose Configuration

```yaml
version: '3.8'
services:
  ytdl-service:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./downloads:/opt/ytdl_service/downloads
      - ./logs:/var/log
      - ./config:/opt/ytdl_service/config
    environment:
      - YTDL_SERVICE_URL=http://localhost:8000
      - PORT=8000
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## Error Handling

### Container Startup Errors

1. **Missing Dependencies**: 
   - Dockerfile ensures all dependencies are installed
   - Multi-stage build validates requirements

2. **Permission Issues**:
   - Non-root user creation with proper permissions
   - Volume mount permission handling

3. **Configuration Errors**:
   - Environment variable validation
   - Graceful fallbacks for optional configuration

### Runtime Error Handling

1. **Service Health Monitoring**:
   - Health check endpoint implementation
   - Container restart policies
   - Log aggregation for debugging

2. **Volume Mount Issues**:
   - Directory creation with proper permissions
   - Fallback to container-local storage if volumes fail

3. **Network Connectivity**:
   - Retry mechanisms for external dependencies
   - Graceful degradation when services unavailable

## Testing Strategy

### Container Testing

1. **Build Testing**:
   - Multi-stage build validation
   - Dependency installation verification
   - Security scanning with tools like Trivy

2. **Runtime Testing**:
   - Health check endpoint validation
   - API functionality testing
   - Volume mount verification

3. **Integration Testing**:
   - Docker Compose stack testing
   - Service-to-service communication
   - End-to-end download workflow

### Security Testing

1. **Image Security**:
   - Base image vulnerability scanning
   - Dependency vulnerability assessment
   - Non-root user validation

2. **Runtime Security**:
   - Container escape prevention
   - Resource limit enforcement
   - Secret management validation

### Performance Testing

1. **Resource Usage**:
   - Memory consumption monitoring
   - CPU usage optimization
   - Disk I/O performance

2. **Scalability Testing**:
   - Multiple container deployment
   - Load balancing verification
   - Concurrent download handling

## Deployment Strategies

### Single Container Deployment

```bash
# Build and run single container
docker build -t ytdl-service .
docker run -d \
  --name ytdl-service \
  -p 8000:8000 \
  -v $(pwd)/downloads:/opt/ytdl_service/downloads \
  -v $(pwd)/logs:/var/log \
  -e YTDL_SERVICE_URL=http://localhost:8000 \
  ytdl-service
```

### Docker Compose Deployment

```bash
# Multi-service orchestration
docker-compose up -d
docker-compose logs -f ytdl-service
docker-compose down
```

### Production Deployment Considerations

1. **Resource Limits**:
   - Memory limits for download operations
   - CPU limits for video processing
   - Disk space monitoring

2. **Monitoring and Logging**:
   - Centralized log aggregation
   - Metrics collection (Prometheus)
   - Alert configuration

3. **Backup and Recovery**:
   - Volume backup strategies
   - Configuration backup
   - Disaster recovery procedures

## Security Considerations

### Container Security

1. **Non-Root User**:
   - Application runs as dedicated user (ytdl:ytdl)
   - Minimal required permissions
   - No sudo or privileged access

2. **Image Hardening**:
   - Minimal base image usage
   - Regular security updates
   - Dependency vulnerability management

3. **Runtime Security**:
   - Read-only root filesystem where possible
   - Resource constraints
   - Network policy enforcement

### Secret Management

1. **API Key Handling**:
   - Environment variable injection
   - File-based secret mounting
   - Automatic key generation fallback

2. **Telegram Bot Security**:
   - Token management through environment variables
   - Secure communication channels
   - Error message sanitization

### Network Security

1. **Port Exposure**:
   - Minimal port exposure (only FastAPI)
   - Internal service communication
   - Firewall configuration guidance

2. **TLS/SSL**:
   - HTTPS termination at reverse proxy
   - Internal HTTP communication
   - Certificate management guidance