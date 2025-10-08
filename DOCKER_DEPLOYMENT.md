# Docker Deployment Guide

## Overview

This guide provides comprehensive instructions for deploying the YouTube Download Service using Docker. The service can be deployed as a standalone container or using Docker Compose for orchestrated deployment.

## Prerequisites

- Docker Engine 20.10+ or Docker Desktop
- Docker Compose 2.0+ (for compose deployments)
- At least 2GB available disk space
- Network access for downloading videos

## Quick Start

### 1. Clone and Build

```bash
# Clone the repository
git clone <repository-url>
cd ytdl-service

# Build the Docker image
./build.sh
```

### 2. Run with Docker Compose (Recommended)

```bash
# Copy environment template
cp .env.example .env

# Edit environment variables as needed
nano .env

# Start the service
docker-compose up -d

# View logs
docker-compose logs -f ytdl-service
```

### 3. Access the Service

- API: http://localhost:8000
- Health Check: http://localhost:8000/health
- API Documentation: http://localhost:8000/docs

## Build Instructions

### Using Build Script (Recommended)

```bash
./build.sh
```

### Manual Build

```bash
# Build the Docker image
docker build -t ytdl-service:latest .

# Build with custom tag
docker build -t ytdl-service:v1.0.0 .

# Build with build arguments
docker build \
  --build-arg PYTHON_VERSION=3.11 \
  -t ytdl-service:latest .
```

### Multi-Architecture Build

```bash
# Build for multiple architectures
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ytdl-service:latest \
  --push .
```

## Deployment Scenarios

### Scenario 1: Standalone Container

Best for: Simple deployments, testing, single-user scenarios

```bash
# Run with default configuration
./run.sh

# Run with custom configuration
docker run -d \
  --name ytdl-service \
  -p 8000:8000 \
  -v $(pwd)/downloads:/opt/ytdl_service/downloads \
  -v $(pwd)/logs:/var/log \
  -e YTDL_SERVICE_URL=http://localhost:8000 \
  -e YTDL_SERVICE_API_KEY=your-secure-api-key \
  ytdl-service:latest
```

### Scenario 2: Docker Compose (Recommended)

Best for: Development, multi-service deployments, easy management

```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d ytdl-service

# Scale the service
docker-compose up -d --scale ytdl-service=3

# Stop services
docker-compose down
```

### Scenario 3: Production Deployment

Best for: Production environments, high availability, monitoring

```bash
# Use production compose file
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# With resource limits
docker run -d \
  --name ytdl-service \
  --memory=2g \
  --cpus=1.5 \
  --restart=unless-stopped \
  -p 8000:8000 \
  -v /data/ytdl/downloads:/opt/ytdl_service/downloads \
  -v /data/ytdl/logs:/var/log \
  -e YTDL_SERVICE_URL=https://ytdl.yourdomain.com \
  -e YTDL_SERVICE_API_KEY=your-secure-api-key \
  ytdl-service:latest
```

### Scenario 4: Behind Reverse Proxy

Best for: HTTPS termination, load balancing, domain routing

```bash
# Run service on internal port
docker run -d \
  --name ytdl-service \
  --network reverse-proxy \
  -e YTDL_SERVICE_URL=https://ytdl.yourdomain.com \
  -e PORT=8000 \
  -v /data/ytdl/downloads:/opt/ytdl_service/downloads \
  -v /data/ytdl/logs:/var/log \
  ytdl-service:latest
```

Example Nginx configuration:
```nginx
server {
    listen 443 ssl;
    server_name ytdl.yourdomain.com;
    
    location / {
        proxy_pass http://ytdl-service:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Management Commands

### Container Management

```bash
# Start container
./run.sh

# Stop container
./stop.sh

# View logs
./logs.sh

# Restart container
docker restart ytdl-service

# Update container
docker pull ytdl-service:latest
docker stop ytdl-service
docker rm ytdl-service
./run.sh
```

### Docker Compose Management

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart services
docker-compose restart

# Update services
docker-compose pull
docker-compose up -d

# View service status
docker-compose ps

# View logs
docker-compose logs -f ytdl-service
```

## Health Monitoring

### Health Check Endpoint

```bash
# Check service health
curl http://localhost:8000/health

# Expected response
{
  "status": "healthy",
  "timestamp": "2025-01-08T10:30:00Z",
  "version": "1.0.0",
  "checks": {
    "disk_space": "ok",
    "dependencies": "ok"
  }
}
```

### Container Health Status

```bash
# Check container health
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# View health check logs
docker inspect ytdl-service --format='{{json .State.Health}}'
```

## Security Considerations

### Container Security

- Service runs as non-root user (ytdl:ytdl)
- Minimal base image (python:3.11-slim-bullseye)
- No unnecessary ports exposed
- Read-only root filesystem where possible

### API Security

```bash
# Generate secure API key
openssl rand -hex 32

# Set API key via environment
export YTDL_SERVICE_API_KEY=$(openssl rand -hex 32)
```

### Network Security

```bash
# Run on custom network
docker network create ytdl-network
docker run -d \
  --name ytdl-service \
  --network ytdl-network \
  -p 127.0.0.1:8000:8000 \
  ytdl-service:latest
```

## Performance Tuning

### Resource Limits

```bash
# Set memory and CPU limits
docker run -d \
  --name ytdl-service \
  --memory=2g \
  --memory-swap=2g \
  --cpus=1.5 \
  --oom-kill-disable=false \
  ytdl-service:latest
```

### Storage Optimization

```bash
# Use tmpfs for temporary files
docker run -d \
  --name ytdl-service \
  --tmpfs /tmp:rw,size=1g \
  -v $(pwd)/downloads:/opt/ytdl_service/downloads \
  ytdl-service:latest
```

## Backup and Recovery

See [Volume Management and Backup Guide](VOLUME_MANAGEMENT.md) for detailed backup strategies.

## Troubleshooting

See [Troubleshooting Guide](TROUBLESHOOTING.md) for common issues and solutions.

## Environment Variables

See [Environment Variables Guide](ENVIRONMENT_VARIABLES.md) for complete configuration options.